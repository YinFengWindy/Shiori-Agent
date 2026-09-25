from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from unittest.mock import AsyncMock
from core.roles.reply_state import InvalidRoleReply, RoleReply, reply_state_metadata
from agent.looping.ports import SessionServices
from agent.turns.orchestrator import TurnOrchestrator, TurnOrchestratorDeps
from agent.turns.outbound import DeliveryReceipt
from session.manager import SessionManager
from session.manager.models import build_session_message
from types import SimpleNamespace

from tests.backend.proactive_v2.conftest import (
    make_proactive_pipeline,
    relationship_gate_chain,
)


class _ScriptedLlm:
    def __init__(self, responses: list[dict[str, Any] | None]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict[str, Any]]] = []
        self.tool_choices: list[str | dict[str, Any]] = []

    async def __call__(
        self,
        messages: list[dict[str, Any]],
        _schemas: list[dict[str, Any]],
        tool_choice: str | dict[str, Any] = "auto",
    ) -> dict[str, Any] | None:
        self.calls.append(list(messages))
        self.tool_choices.append(tool_choice)
        return self._responses.pop(0) if self._responses else None


def _scene_followup_gate(_session_key: str, _now: datetime):
    return True, {"reason": "scene_followup_due", "attempt_index": 0}


@pytest.mark.asyncio
async def test_scene_followup_retries_plain_text_response_as_required_tool_call():
    sent_calls: list[tuple[str, datetime]] = []
    llm = _ScriptedLlm(
        [
            None,
            {
                "name": "message_push",
                "input": {
                    "mood": "平静",
                    "thought": "我想和你聊聊。",
                    "message": "还不理我吗？",
                    "evidence": [],
                },
            },
            {"name": "finish_turn", "input": {"decision": "reply"}},
        ]
    )
    pipeline = make_proactive_pipeline(
        llm_fn=llm,
        proactive_gates=relationship_gate_chain(
            scene_evaluate=_scene_followup_gate,
            on_scene_delivered=lambda session_key, now: sent_calls.append(
                (session_key, now)
            ),
            loneliness_evaluate=lambda _session_key, _now: (
                False,
                {"reason": "below_threshold"},
            ),
        ),
    )

    await pipeline.run()

    assert pipeline.last_ctx is not None
    assert pipeline.last_ctx.terminal_action == "reply"
    assert llm.tool_choices == ["required", "required", "required"]
    assert "必须返回一个工具调用" in str(llm.calls[1][-1]["content"])
    assert len(sent_calls) == 1


@pytest.mark.asyncio
async def test_scene_followup_protocol_failure_preserves_pending_scene():
    closed_sessions: list[str] = []
    llm = _ScriptedLlm([None, None])
    pipeline = make_proactive_pipeline(
        llm_fn=llm,
        proactive_gates=relationship_gate_chain(
            scene_evaluate=_scene_followup_gate,
            on_scene_closed=closed_sessions.append,
            loneliness_evaluate=lambda _session_key, _now: (
                False,
                {"reason": "below_threshold"},
            ),
        ),
    )

    await pipeline.run()

    assert pipeline.last_ctx is not None
    assert pipeline.last_ctx.terminal_action is None
    assert pipeline.last_ctx.skip_reason == "tool_protocol_error"
    assert llm.tool_choices == ["required", "required"]
    assert closed_sessions == []


@pytest.mark.asyncio
async def test_tool_protocol_retry_and_missing_mood_share_one_tick_correction():
    sender = SimpleNamespace(send=AsyncMock(return_value=True))
    llm = _ScriptedLlm(
        [
            None,
            {
                "name": "message_push",
                "input": {"message": "hi", "thought": "我想聊聊。"},
            },
            {
                "name": "message_push",
                "input": {"message": "hi", "mood": "平静", "thought": "我想聊聊。"},
            },
        ]
    )
    pipeline = make_proactive_pipeline(
        llm_fn=llm,
        sender=sender,
        proactive_gates=relationship_gate_chain(scene_evaluate=_scene_followup_gate),
    )
    with pytest.raises(InvalidRoleReply):
        await pipeline.run()
    assert len(llm.calls) == 2
    assert pipeline.last_ctx.reply_format_corrections == 1
    sender.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_tick_captures_state_before_generation_and_does_not_send_stale_reply(
    tmp_path,
):
    sessions = SessionManager(tmp_path)
    session = sessions.open_role_session("mira", role_name="Mira")
    outbound = SimpleNamespace(dispatch=AsyncMock(return_value=DeliveryReceipt()))
    owner = TurnOrchestrator(TurnOrchestratorDeps(SessionServices(sessions), outbound))
    calls = 0

    async def llm(_messages, _schemas, _tool_choice):
        nonlocal calls
        calls += 1
        if calls == 1:
            await sessions.append_messages(
                session,
                [build_session_message("assistant", "new passive")],
                pending_messages=True,
                expected_mood_updated_at="",
                metadata_updates=reply_state_metadata(
                    RoleReply("new passive", "平静", "我已经回来了。"),
                    updated_at="new-passive",
                ),
            )
            return {
                "name": "message_push",
                "input": {
                    "message": "old proactive",
                    "mood": "平静",
                    "thought": "我还在等你。",
                },
            }
        return {"name": "finish_turn", "input": {"decision": "reply"}}

    pipeline = make_proactive_pipeline(
        session_key=session.key,
        llm_fn=llm,
        target_transport_fn=lambda: ("telegram", "123"),
    )
    pipeline._turn_orchestrator = owner
    with pytest.raises(ValueError, match="过时"):
        await pipeline.run()
    assert pipeline.last_ctx.reply_context.previous_updated_at == ""
    assert session.metadata["current_thought"] == "我已经回来了。"
    assert [m["content"] for m in session.messages] == ["new passive"]
    outbound.dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_normal_tick_corrects_state_without_replaying_earlier_tool(tmp_path):
    sessions = SessionManager(tmp_path)
    session = sessions.open_role_session("mira", role_name="Mira")
    outbound = SimpleNamespace(dispatch=AsyncMock(return_value=DeliveryReceipt()))
    owner = TurnOrchestrator(TurnOrchestratorDeps(SessionServices(sessions), outbound))
    llm = _ScriptedLlm(
        [
            {"name": "get_recent_chat", "input": {}},
            {
                "name": "message_push",
                "input": {"message": "hi", "thought": "我放心了。"},
            },
            {
                "name": "message_push",
                "input": {"message": "hi", "mood": "平静", "thought": "我放心了。"},
            },
            {"name": "finish_turn", "input": {"decision": "reply"}},
        ]
    )
    pipeline = make_proactive_pipeline(
        session_key=session.key,
        llm_fn=llm,
        target_transport_fn=lambda: ("telegram", "123"),
    )
    pipeline._turn_orchestrator = owner
    recent = pipeline._tool_deps.recent_chat_fn
    await pipeline.run()
    recent.assert_awaited_once()
    assert len(llm.calls) == 4
    assert pipeline.last_ctx.steps_taken == 4
    assert session.metadata["current_thought"] == "我放心了。"
    assert session.messages[-1]["content"] == "hi"
    assert outbound.dispatch.await_args.args[0].content == "hi"
