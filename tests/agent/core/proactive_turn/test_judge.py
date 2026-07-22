from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from tests.proactive_v2.conftest import (
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
                "input": {"message": "还不理我吗？", "evidence": []},
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
