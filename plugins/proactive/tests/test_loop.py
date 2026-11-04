from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from plugins.proactive.backend.loop import ProactiveLoop


class _Sessions:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def role_session_key(self, role_id: str) -> str:
        return f"role:{role_id}"


def _bare_run_loop(tmp_path: Path) -> ProactiveLoop:
    """A constructed loop whose run only prepares its state and first poll."""
    loop = ProactiveLoop.__new__(ProactiveLoop)
    loop._cfg = SimpleNamespace(role_id="mira", enabled=True)
    loop._state = None
    loop._sessions = _Sessions(tmp_path)
    loop._init_runtime_state()
    loop._state_path = tmp_path / "proactive.db"
    loop._init_runtime_components = lambda: None
    return loop


@pytest.mark.asyncio
async def test_run_closes_state_when_cancelled_during_first_poll(tmp_path: Path):
    loop = _bare_run_loop(tmp_path)
    polling = asyncio.Event()

    async def first_poll():
        polling.set()
        await asyncio.Event().wait()

    async def run_loop():
        await loop._prepare()

    loop._poll_feeds_once = first_poll
    loop._run_loop = run_loop
    run = asyncio.create_task(loop.run())
    await polling.wait()
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
    assert loop._state is None


@pytest.mark.asyncio
async def test_run_reports_a_failed_feed_poll(tmp_path: Path):
    loop = _bare_run_loop(tmp_path)

    async def failing_poll():
        raise OSError("poll failed")

    async def run_loop():
        loop._prepared = True
        loop._poll_task = asyncio.create_task(failing_poll())
        await asyncio.sleep(0)

    loop._run_loop = run_loop
    with pytest.raises(OSError, match="poll failed"):
        await loop.run()


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
    loop._cfg = SimpleNamespace(role_id="mira")
    loop._sessions = _Sessions(tmp_path)
    (tmp_path / "AGENTS.md").write_text("guide", encoding="utf-8")

    assert loop._sample_random_memory(1)


@pytest.mark.asyncio
async def test_tick_target_error_is_logged_at_loop_boundary_and_loop_continues(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    from plugins.proactive.backend.turn.delivery import resolve_target_transport
    from plugins.proactive.backend.sensor import Sensor

    # Without a target resolver every tick fails when it picks its target.
    sensor = Sensor(
        cfg=SimpleNamespace(role_id="mira"),
        sessions=_Sessions(tmp_path),
        state=SimpleNamespace(),
        memory=None,
        presence=None,
        rng=None,
    )
    ticks = 0

    async def run_tick():
        nonlocal ticks
        ticks += 1
        if ticks == 2:
            loop.stop()
        return resolve_target_transport(sensor.target_transport)

    loop = ProactiveLoop.__new__(ProactiveLoop)
    loop._running = True
    loop._cfg = SimpleNamespace(enabled=True, role_id="mira")
    loop._config_fn = None
    loop._next_interval = lambda base_score=None: 0
    loop._wait_interval = AsyncMock(return_value=None)
    loop._run_tick = run_tick

    with caplog.at_level("INFO", logger="plugins.proactive.backend.loop"):
        await loop._run_loop()

    # Both ticks ran: the first failure did not end the loop.
    assert ticks == 2
    failures = [r for r in caplog.records if r.message == "ProactiveLoop tick 异常"]
    assert len(failures) == 2
    assert all(r.levelname == "ERROR" and r.exc_info for r in failures)
    assert "主动推送缺少目标选择服务: mira" in caplog.text
