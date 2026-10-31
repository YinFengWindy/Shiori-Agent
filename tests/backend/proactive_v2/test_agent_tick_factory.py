from __future__ import annotations

from plugins.natural_chat.backend.plugin import NaturalChatPolicy
from tests.support.generation_getters import turn_getters
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
        presence=SimpleNamespace(last_user_at=lambda _: None),
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

    from core.roles.store import RoleStore

    manager = SessionManager(tmp_path)
    manager.get_or_create("role:mira").metadata.update(
        role_id="mira", role_runtime_config={"natural_chat_enabled": False}
    )
    roles = RoleStore(tmp_path)
    roles.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="test",
        runtime_config={"natural_chat_enabled": True},
    )
    dispatch = AsyncMock(return_value=DeliveryReceipt.sent())
    owner = TurnOrchestrator(
        TurnOrchestratorDeps(
            session=SessionServices(manager),
            outbound=SimpleNamespace(dispatch=dispatch),
            role_lookup=roles.get_role,
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

    class _Host:
        def natural_reply_active(self) -> bool:
            return current_proactive_reply() is not None

        def reply_invalidated(self) -> bool:
            from agent.turns.reply_interruption import reply_was_invalidated

            return reply_was_invalidated()

        def mcp_server_names(self) -> tuple[str, ...]:
            return ()

        def recent_activity(self, role_id: str, *, now: object) -> str:
            del role_id, now
            return ""

        def tool_schemas(self, names: object = None) -> tuple[object, ...]:
            del names
            return ()

        def validate_reply(
            self,
            role_id: str,
            *,
            content: str,
            mood: str,
            thought: str,
            allow_empty_content: bool = False,
        ):
            from core.roles.reply_state import validate_role_reply
            from shiori_sdk.core.proactive_host import ValidatedRoleReply

            del role_id
            reply = validate_role_reply(
                {"content": content, "mood": mood, "thought": thought},
                ("平静",),
                allow_empty_content=allow_empty_content,
            )
            return ValidatedRoleReply(
                content=reply.content, mood=reply.mood, thought=reply.thought
            )

        async def complete(
            self,
            messages,
            *,
            tools=(),
            tool_choice="auto",
            max_tokens=None,
            call_purpose="default",
            disable_thinking=True,
            defer_tool_argument_errors=False,
            natural_draft=False,
        ):
            from proactive_v2.reply_output import complete_natural_push
            from shiori_sdk.core.proactive_host import (
                CompletionToolCall,
                ModelCompletion,
            )

            kwargs = {
                "messages": list(messages),
                "tools": list(tools),
                "model": deps.model,
                "max_tokens": max_tokens,
                "tool_choice": tool_choice,
                "disable_thinking": disable_thinking,
                "call_purpose": call_purpose,
            }
            if defer_tool_argument_errors:
                kwargs["defer_tool_argument_errors"] = True
            resp = await chat(**kwargs)
            if natural_draft:
                resp = await complete_natural_push(
                    resp,
                    messages=list(messages),
                    provider=SimpleNamespace(chat=chat),
                    model=deps.model,
                    max_tokens=max_tokens,
                )
            calls = tuple(
                CompletionToolCall(
                    id=call.id,
                    name=call.name,
                    arguments=dict(call.arguments),
                    raw_arguments=call.raw_arguments,
                    arguments_error=call.arguments_error,
                )
                for call in (resp.tool_calls or [])
            )
            return ModelCompletion(
                content=resp.content or "",
                tool_calls=calls,
                thinking=resp.thinking,
            )

        async def retarget_natural_transport(
            self, session_key, channel, chat_id
        ) -> None:
            await owner.retarget_natural_transport(session_key, channel, chat_id)

        async def commit_natural_reply(self, reply):
            from conversation.initiated import _turn_result
            from shiori_sdk.core.conversation import InitiatedDelivery

            committed: list[str] = []
            complete = await owner.handle_proactive_turn(
                result=_turn_result(reply, include_target=False),
                session_key=reply.session_key,
                channel=reply.channel,
                chat_id=reply.chat_id,
                source=reply.source,
                committed=committed,
            )
            return InitiatedDelivery(message_ids=tuple(committed), complete=complete)

        async def execute_tool(self, call, invoker):
            from shiori_sdk.core.proactive_host import ProactiveToolOutcome

            output = await invoker(call.name, dict(call.arguments))
            return ProactiveToolOutcome(
                text=str(output),
                status="ok",
                arguments=dict(call.arguments),
            )

    deps.provider = SimpleNamespace(chat=chat)
    deps.proactive_host = _Host()
    factory = AgentTickFactory(deps)
    drift = factory._build_drift_pipeline(ToolDeps())
    assert drift is not None
    ctx = AgentTickContext(
        session_key="role:mira", reply_context=owner.capture_reply_context("role:mira")
    )
    monkeypatch.setattr("agent.turns.reply_sequence.wait_between_messages", AsyncMock())
    batches = ChannelSequenceOwner()
    # The natural_chat plugin is on, as the drift tick's lease would say.
    with turn_getters(policy=NaturalChatPolicy()), batches.bind(MessageBus()):
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
