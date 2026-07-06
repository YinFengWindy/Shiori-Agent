"""
TDD — ProactiveTurnPipeline pre-gate

当前主动链路只保留：
  - target transport
  - passive busy
  - loneliness threshold
其余 AnyAction / 旧 delivery cooldown / context-only 配额不再作为前置限制。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.proactive_v2.conftest import (
    FakeLLM,
    FakeRng,
    FakeStateStore,
    cfg_with,
    make_proactive_pipeline,
)


@pytest.mark.asyncio
async def test_no_target_blocks_when_transport_missing():
    tick = make_proactive_pipeline(
        cfg=cfg_with(default_channel="", default_chat_id=""),
        target_transport_fn=lambda: ("", ""),
    )
    result = await tick.run()
    assert result is None


@pytest.mark.asyncio
async def test_passive_busy_returns_none():
    state = FakeStateStore()
    tick = make_proactive_pipeline(passive_busy_fn=lambda sk: True, state_store=state)
    result = await tick.run()
    assert result is None
    assert len(state.tick_log_finishes) == 1
    assert state.tick_log_finishes[0]["gate_exit"] == "busy"
    assert state.tick_log_finishes[0]["terminal_action"] is None


@pytest.mark.asyncio
async def test_passive_busy_false_does_not_block():
    tick = make_proactive_pipeline(
        passive_busy_fn=lambda sk: False,
        loneliness_gate_fn=lambda _session_key, _now_utc: (True, {"reason": "threshold"}),
    )
    result = await tick.run()
    assert result is not None


@pytest.mark.asyncio
async def test_passive_busy_receives_session_key():
    received = []
    tick = make_proactive_pipeline(
        session_key="my_session",
        passive_busy_fn=lambda sk: received.append(sk) or False,
        loneliness_gate_fn=lambda _session_key, _now_utc: (True, {"reason": "threshold"}),
    )
    await tick.run()
    assert received == ["my_session"]


@pytest.mark.asyncio
async def test_target_transport_allows_role_only_desktop_target():
    tick = make_proactive_pipeline(
        cfg=cfg_with(default_channel="desktop", default_chat_id=""),
        target_transport_fn=lambda: ("desktop", "role:mira"),
        loneliness_gate_fn=lambda _session_key, _now_utc: (True, {"reason": "threshold"}),
    )
    result = await tick.run()
    assert result is not None


@pytest.mark.asyncio
async def test_loneliness_gate_blocks_when_threshold_not_reached():
    state = FakeStateStore()
    gate_calls: list[tuple[str, datetime]] = []
    tick = make_proactive_pipeline(
        state_store=state,
        loneliness_gate_fn=lambda session_key, now_utc: (
            gate_calls.append((session_key, now_utc)) or False,
            {"reason": "below_threshold"},
        ),
    )
    result = await tick.run()
    assert result is None
    assert len(gate_calls) == 1
    assert gate_calls[0][0] == "test_session"
    assert state.tick_log_finishes[0]["gate_exit"] == "loneliness"


@pytest.mark.asyncio
async def test_loneliness_gate_passes_when_threshold_reached():
    tick = make_proactive_pipeline(
        loneliness_gate_fn=lambda _session_key, _now_utc: (True, {"reason": "threshold"}),
    )
    result = await tick.run()
    assert result is not None


@pytest.mark.asyncio
async def test_empty_candidates_skip_without_llm():
    llm = FakeLLM([("get_recent_chat", {})])
    tick = make_proactive_pipeline(
        llm_fn=llm,
        rng=FakeRng(value=1.0),
        loneliness_gate_fn=lambda _session_key, _now_utc: (True, {"reason": "threshold"}),
    )
    result = await tick.run()
    assert result == 0.0
    assert llm.calls == []
    assert tick.last_ctx.skip_reason == "no_content"


@pytest.mark.asyncio
async def test_drift_interval_blocks_recent_drift():
    state = FakeStateStore()
    state.set_last_drift_at(datetime.now(timezone.utc) - timedelta(hours=1))
    drift_pipeline = MagicMock()
    tick = make_proactive_pipeline(
        cfg=cfg_with(drift_enabled=True, drift_min_interval_hours=3),
        state_store=state,
        rng=FakeRng(value=1.0),
        llm_fn=AsyncMock(return_value=None),
        drift_pipeline=drift_pipeline,
        loneliness_gate_fn=lambda _session_key, _now_utc: (True, {"reason": "threshold"}),
    )
    await tick.run()
    assert tick.last_ctx.drift_entered is False
    assert tick.last_ctx.skip_reason == "no_content"
    drift_pipeline.run.assert_not_called()


@pytest.mark.asyncio
async def test_drift_interval_allows_after_window():
    from agent.core.drift_turn import DriftTurnPipeline, DriftTurnPipelineDeps
    from proactive_v2.drift_state import DriftStateStore
    from proactive_v2.drift_tools import DriftToolDeps
    from pathlib import Path
    import tempfile

    state = FakeStateStore()
    state.set_last_drift_at(datetime.now(timezone.utc) - timedelta(hours=4))
    llm = FakeLLM([
        (
            "finish_drift",
            {
                "skill_used": "explore-curiosity",
                "one_line": "x",
                "next": "y",
                "message_result": "silent",
            },
        ),
    ])
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        skill_dir = tmp_path / "skills" / "explore-curiosity"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: explore-curiosity\ndescription: x\n---\n",
            encoding="utf-8",
        )
        tick = make_proactive_pipeline(
            cfg=cfg_with(drift_enabled=True, drift_min_interval_hours=3),
            state_store=state,
            llm_fn=llm,
            rng=FakeRng(value=1.0),
            drift_pipeline=DriftTurnPipeline(
                DriftTurnPipelineDeps(
                    store=DriftStateStore(tmp_path),
                    tool_deps=DriftToolDeps(
                        drift_dir=tmp_path,
                        store=DriftStateStore(tmp_path),
                    ),
                    max_steps=5,
                )
            ),
            loneliness_gate_fn=lambda _session_key, _now_utc: (True, {"reason": "threshold"}),
        )
        await tick.run()
        assert tick.last_ctx.drift_entered is True
        assert state.drift_run_marked is True


@pytest.mark.asyncio
async def test_pregate_fail_does_not_call_alert_fn():
    alert_fn = AsyncMock(return_value=[])
    from proactive_v2.tools import ToolDeps
    from proactive_v2.gateway import GatewayDeps

    deps = ToolDeps()
    tick = make_proactive_pipeline(
        passive_busy_fn=lambda sk: True,
        tool_deps=deps,
        gateway_deps=GatewayDeps(
            alert_fn=alert_fn,
            feed_fn=AsyncMock(return_value=[]),
        ),
        loneliness_gate_fn=lambda _session_key, _now_utc: (True, {"reason": "threshold"}),
    )
    await tick.run()
    alert_fn.assert_not_called()


@pytest.mark.asyncio
async def test_all_gates_pass_returns_non_none():
    tick = make_proactive_pipeline(
        passive_busy_fn=lambda sk: False,
        loneliness_gate_fn=lambda _session_key, _now_utc: (True, {"reason": "threshold"}),
    )
    result = await tick.run()
    assert result is not None
