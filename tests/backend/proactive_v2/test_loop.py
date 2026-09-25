from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from proactive_v2.config import ProactiveConfig
from proactive_v2.loop import ProactiveLoop


class _ProactiveTraceLoop(ProactiveLoop):
    def __init__(self, workspace: Path, *, role_id: str = "") -> None:
        self._sessions = SimpleNamespace(workspace=workspace)
        self._cfg = SimpleNamespace(
            enabled=True,
            default_role_id=role_id,
            score_llm_threshold=0.6,
            tick_interval_s0=30,
            tick_interval_s1=60,
            tick_jitter=0.1,
            anyaction_enabled=True,
            anyaction_min_interval_seconds=60,
            anyaction_probability_min=0.1,
            anyaction_probability_max=0.5,
            memory_history_gate_enabled=True,
        )


def test_proactive_trace_uses_global_subject_without_role(tmp_path: Path):
    loop = _ProactiveTraceLoop(tmp_path)
    loop._trace_proactive_rate_decision(base_score=0.5, interval=60, mode="adaptive")

    trace_path = tmp_path / "memory" / "proactive_rate_trace.jsonl"
    line = json.loads(trace_path.read_text(encoding="utf-8").strip())
    assert line["trace_type"] == "proactive_rate"
    assert line["subject"] == {"kind": "global", "id": "proactive_rate_trace"}
    assert line["payload"]["mode"] == "adaptive"


def test_proactive_trace_uses_role_subject_when_configured(tmp_path: Path):
    loop = _ProactiveTraceLoop(tmp_path, role_id="mira")
    loop._trace_proactive_rate_decision(base_score=0.5, interval=60, mode="adaptive")

    trace_path = tmp_path / "memory" / "proactive_rate_trace.jsonl"
    line = json.loads(trace_path.read_text(encoding="utf-8").strip())
    assert line["subject"] == {"kind": "role", "id": "mira"}


@pytest.mark.asyncio
async def test_proactive_loop_wrapper_methods_cover_paths(tmp_path: Path):
    loop = ProactiveLoop.__new__(ProactiveLoop)
    loop._cfg = ProactiveConfig(
        interval_seconds=10,
        score_weight_energy=0.5,
        tick_interval_s1=3,
        tick_interval_s0=4,
        tick_jitter=0.0,
        default_channel="telegram",
        default_chat_id="42",
    )
    loop._trace_proactive_rate_decision = MagicMock()
    loop._presence = SimpleNamespace(
        get_last_user_at=lambda session_key: datetime.now(timezone.utc)
    )
    loop._sense = SimpleNamespace(
        target_session_key=lambda: "telegram:1",
        target_transport=lambda: ("telegram", "1"),
        has_role_memory=lambda: True,
        read_memory_text=lambda: "mem",
        compute_energy=lambda: 0.5,
        compute_interruptibility=lambda **kwargs: (0.5, {"x": 1}),
    )
    loop._rng = None
    loop._memory = SimpleNamespace(
        read_long_term=lambda: "remember", get_memory_context=lambda: "ctx"
    )
    loop._sessions = SimpleNamespace(workspace=tmp_path)
    (tmp_path / "AGENTS.md").write_text("guide", encoding="utf-8")
    loop._sender = SimpleNamespace(send=AsyncMock(return_value=True))
    loop._proactive_pipeline = SimpleNamespace(run=AsyncMock(return_value=0.2))
    loop._init_runtime_state(loop._cfg)
    loop._mcp_pool = SimpleNamespace(
        connect_all=AsyncMock(return_value=None),
        disconnect_all=AsyncMock(return_value=None),
    )
    loop._run_loop = AsyncMock(return_value=None)

    assert loop._has_role_memory() is True
    assert loop._read_memory_text() == "mem"
    assert loop._compute_energy() == 0.5
    assert loop._compute_interruptibility(
        now_hour=10,
        now_utc=datetime.now(timezone.utc),
        recent_msg_count=0,
    ) == (0.5, {"x": 1})
    assert await loop._tick() == 0.2
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("proactive_v2.loop.compute_energy", lambda last_user_at: 0.8)
        mp.setattr("proactive_v2.loop.d_energy", lambda energy: 0.5)
        mp.setattr("proactive_v2.loop.next_tick_from_score", lambda *args, **kwargs: 7)
        assert loop._next_interval() == 7
    await loop.run()
    loop._mcp_pool.connect_all.assert_awaited_once()
    loop._run_loop.assert_awaited_once()
    loop._mcp_pool.disconnect_all.assert_awaited_once()


def test_next_interval_falls_back_to_configured_interval_without_presence():
    """没有 presence 时无法算 energy，应直接用配置的固定间隔。"""
    loop = ProactiveLoop.__new__(ProactiveLoop)
    loop._cfg = SimpleNamespace(
        interval_seconds=10,
        score_weight_energy=0.5,
        tick_interval_s1=3,
        tick_interval_s0=4,
        tick_jitter=0.0,
    )
    loop._presence = None
    loop._trace_proactive_rate_decision = MagicMock()
    loop._sense = SimpleNamespace(target_session_key=lambda: "telegram:1")

    assert loop._next_interval() == 10


def test_sample_random_memory_reads_long_term_and_workspace_guide(tmp_path: Path):
    loop = ProactiveLoop.__new__(ProactiveLoop)
    loop._rng = None
    loop._memory = SimpleNamespace(
        read_long_term=lambda: "remember",
        get_memory_context=lambda: "ctx",
    )
    loop._sessions = SimpleNamespace(workspace=tmp_path)
    (tmp_path / "AGENTS.md").write_text("guide", encoding="utf-8")

    assert loop._sample_random_memory(1)


@pytest.mark.asyncio
async def test_tick_target_error_is_logged_at_loop_boundary_and_loop_continues(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    from agent.core.proactive_turn.delivery import resolve_target_transport
    from proactive_v2.sensor import Sensor
    from session.manager import SessionManager

    # Without a target resolver every tick fails when it picks its target.
    sensor = Sensor(
        cfg=SimpleNamespace(default_role_id="mira"),
        sessions=SessionManager(tmp_path),
        state=SimpleNamespace(),
        memory=None,
        presence=None,
        rng=None,
    )
    host = SimpleNamespace(_target_transport_fn=sensor.target_transport)
    ticks = 0

    async def run_tick():
        nonlocal ticks
        ticks += 1
        if ticks == 2:
            loop.stop()
        return resolve_target_transport(host)

    loop = ProactiveLoop.__new__(ProactiveLoop)
    loop._running = True
    loop._poll_feeds_once = AsyncMock(return_value=None)
    loop._poll_loop = AsyncMock(return_value=None)
    loop._next_interval = lambda base_score=None: 0
    loop._wait_interval = AsyncMock(return_value=None)
    loop._run_tick = run_tick

    with caplog.at_level("INFO", logger="proactive_v2.loop"):
        await loop._run_loop()
    assert loop._poll_task is not None
    await loop._poll_task

    # Both ticks ran: the first failure did not end the loop.
    assert ticks == 2
    failures = [r for r in caplog.records if r.message == "ProactiveLoop tick 异常"]
    assert len(failures) == 2
    assert all(r.levelname == "ERROR" and r.exc_info for r in failures)
    assert "主动推送缺少目标选择服务: mira" in caplog.text
