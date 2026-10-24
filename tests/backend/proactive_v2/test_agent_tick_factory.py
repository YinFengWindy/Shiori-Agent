from __future__ import annotations

import json


from types import SimpleNamespace

import pytest

from agent.core.turn_events import core_kernel
from proactive_v2.agent_tick_factory import AgentTickDeps, AgentTickFactory
from proactive_v2.context import AgentTickContext
from proactive_v2.mcp_sources import McpClientPool


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
        kernel=core_kernel,
        pool=McpClientPool() if with_pool else None,
    )
    return deps


@pytest.mark.parametrize("late_target", [False, True, "revoked", "admitted"])
@pytest.mark.parametrize("needs_correction", [False, True])
async def test_natural_drift_uses_shared_messages_and_preserves_thinking(
    tmp_path, monkeypatch, needs_correction, late_target
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
    from agent.account_delivery import AccountDelivery
    from core.accounts import AccountRegistry
    from core.accounts.delivery_ledger import AccountDeliveryLedger
    from core.identity import UserIdentityStore
    from shiori_sdk.accounts.targets import AccountTarget

    accounts = AccountRegistry(lambda role_id: role_id == "mira")
    record = accounts.register(
        plugin_id="telegram",
        platform="telegram",
        platform_account_id="bot",
        config_ref="bot",
        role_id="mira",
        token="live",
    )
    accounts.report(record.record.id, "live", connection="online")
    routed = []

    async def account_send(payload):
        routed.append(payload)
        return {"message_id": f"sent-{len(routed)}"}

    def rpc(method):
        assert method == "plugin.telegram.account.send"
        return "telegram", account_send

    owner._account_delivery = AccountDelivery(
        accounts,
        SimpleNamespace(resolve=rpc),
        AccountDeliveryLedger(tmp_path),
        UserIdentityStore(tmp_path),
    )
    owner._bound_chat_target = lambda role_id, channel, chat: (
        "telegram",
        AccountTarget("private", "user42"),
    )
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
            if late_target:
                deps.sense.target_transport = lambda: ("telegram", "42")
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
    batches = ChannelSequenceOwner()
    with batches.bind(MessageBus()):
        async with owner.natural_reply_scope(
            "role:mira", "desktop", "role:mira", turn_id="drift:test"
        ):
            if late_target == "revoked":
                accounts.release(record.record.id, "live")
            if late_target == "admitted":
                import asyncio
                from shiori_sdk.messages import InboundMessage

                batches.admit(
                    InboundMessage(
                        "telegram",
                        "user42",
                        "42",
                        "已准入的新消息",
                        metadata={
                            "role_id": "mira",
                            "account_id": record.record.id,
                            "chat_type": "private",
                        },
                    )
                )
                with pytest.raises(asyncio.CancelledError):
                    await drift.run(ctx, factory._build_llm_fn())
            else:
                assert await drift.run(ctx, factory._build_llm_fn())
            plan = current_proactive_reply()
            assert plan is not None and plan.completion is not None
            assert plan.protocol.reply is not None
            assert plan.protocol.reply.raw_text == raw
            assert plan.completion.response.thinking == "保留正常思考"
            assert plan.completion.total_tokens == (18 if needs_correction else 11)
    if late_target in {"revoked", "admitted"}:
        assert not ctx.drift_finished and not ctx.drift_message_sent
        dispatch.assert_not_awaited()
        assert routed == []
        assert SessionManager(tmp_path).get_or_create("role:mira").messages == []
        deps.state_store.mark_delivery.assert_not_called()
        return
    assert ctx.drift_finished and ctx.drift_message_sent
    assert [call.args[0].content for call in dispatch.await_args_list] == (
        [] if late_target else expected
    )
    assert [payload["message"] for payload in routed] == (
        expected if late_target else []
    )
    assert all(payload["target_id"] == "user42" for payload in routed)
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
