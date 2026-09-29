from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, cast
from unittest.mock import AsyncMock

import pytest

from agent.core.types import HistoryMessage
from agent.lifecycle.types import AfterTurnCtx, BeforeTurnCtx
from core.scene.state import SceneStateStore
from bus.event_bus import EventBus
from bus.events_lifecycle import (
    ProactiveMessageCommitted,
    SceneObservationCommitted,
)
from core.roles.store import RoleStore
from core.scene.contracts import SceneDecisionProtocolError
from core.scene.controller import SceneAwarenessController
from core.scene.decision import SceneDecision
from session.manager import SessionManager
from bootstrap.runtime.generations import RuntimeCandidate
from core.common.runtime_scope import bind_runtime, current_runtime_lease


def _controller(
    tmp_path: Path,
    *,
    event_bus: EventBus,
    decision_provider: AsyncMock,
) -> SceneAwarenessController:
    role_store = RoleStore(tmp_path)
    _ = role_store.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="粉发少女",
        runtime_config={"test_scene_observation_requested": True},
    )
    sessions = SessionManager(tmp_path)
    sessions.open_role_session("mira", role_name="Mira")
    return SceneAwarenessController(
        role_store=role_store,
        session_manager=sessions,
        event_bus=event_bus,
        kv_store=SceneStateStore(tmp_path),
        needs_observation=lambda role: bool(
            role.runtime_config.get("test_scene_observation_requested")
        )
        or role.proactive.enabled,
        light_provider=cast(Any, object()),
        light_model="light-model",
        decision_provider=decision_provider,
    )


@pytest.mark.asyncio
async def test_scene_task_prevents_retired_runtime_from_terminating_its_controller(
    tmp_path,
):
    controller = _controller(
        tmp_path, event_bus=EventBus(), decision_provider=AsyncMock()
    )
    started, finish = asyncio.Event(), asyncio.Event()
    observed = []

    async def run(*args, **kwargs):
        observed.append(current_runtime_lease().generation)
        started.set()
        await finish.wait()

    controller._run = run
    core = SimpleNamespace(
        stop=AsyncMock(side_effect=controller.terminate),
        memory_runtime=SimpleNamespace(aclose=AsyncMock()),
    )
    generation = RuntimeCandidate(3, core, SimpleNamespace())
    parent = generation.acquire()
    with bind_runtime(parent):
        controller._schedule(
            SimpleNamespace(session_key="role:mira"), assistant_reply="scene"
        )
    await parent.release()
    await generation.retire()
    await asyncio.wait_for(started.wait(), timeout=1)
    core.stop.assert_not_awaited()
    finish.set()
    await asyncio.wait_for(generation.drained.wait(), timeout=1)
    assert observed == [3]
    core.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_passive_turn_publishes_started_scene_and_persists_scene_key(
    tmp_path: Path,
) -> None:
    bus = EventBus()
    observations: list[SceneObservationCommitted] = []
    bus.on(SceneObservationCommitted, observations.append)
    decide = AsyncMock(
        return_value=SceneDecision(
            transition="started",
            scene_key="rain",
            visual_key="rain-standing",
            visual_description="粉发少女站在雨里",
        )
    )
    controller = _controller(tmp_path, event_bus=bus, decision_provider=decide)

    controller.capture_passive_turn(
        BeforeTurnCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            content="下雨了吗？",
            timestamp=datetime.now(),
            retrieved_memory_block="",
            retrieval_trace_raw=None,
            history_messages=(),
        )
    )
    controller.schedule_passive_turn(
        AfterTurnCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            reply="她站在雨里。",
            tools_used=(),
            thinking=None,
            will_dispatch=True,
        )
    )
    await asyncio.gather(*controller.tasks.values())

    assert observations[0].transition == "started"
    assert observations[0].source == "passive"
    assert decide.await_args.kwargs["decision_input"].current_scene_key == ""
    assert decide.await_args.kwargs["decision_input"].current_visual_key == ""

    controller.capture_passive_turn(
        BeforeTurnCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            content="还在下吗？",
            timestamp=datetime.now(),
            retrieved_memory_block="",
            retrieval_trace_raw=None,
            history_messages=(),
        )
    )
    assert (
        controller._pending_turns["role:mira"].decision_input.current_scene_key
        == "rain"
    )
    assert (
        controller._pending_turns["role:mira"].decision_input.current_visual_key
        == "rain-standing"
    )
    await controller.terminate()


@pytest.mark.asyncio
async def test_passive_turn_observes_reply_returned_by_desktop_bridge(
    tmp_path: Path,
) -> None:
    bus = EventBus()
    observations: list[SceneObservationCommitted] = []
    bus.on(SceneObservationCommitted, observations.append)
    decide = AsyncMock(
        return_value=SceneDecision(
            transition="started",
            scene_key="kitchen",
            visual_key="kitchen-cooking",
            visual_description="粉发少女站在雨里",
        )
    )
    controller = _controller(tmp_path, event_bus=bus, decision_provider=decide)

    controller.capture_passive_turn(
        BeforeTurnCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            content="晚饭做什么？",
            timestamp=datetime.now(),
            retrieved_memory_block="",
            retrieval_trace_raw=None,
            history_messages=(),
        )
    )
    controller.schedule_passive_turn(
        AfterTurnCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            reply="她正在厨房里准备晚饭。",
            tools_used=(),
            thinking=None,
            will_dispatch=False,
        )
    )
    await asyncio.gather(*controller.tasks.values())

    assert decide.await_count == 1
    assert observations[0].transition == "started"
    assert observations[0].scene_key == "kitchen"
    await controller.terminate()


@pytest.mark.asyncio
async def test_passive_turn_publishes_none_without_persisting_scene_key(
    tmp_path: Path,
) -> None:
    bus = EventBus()
    observations: list[SceneObservationCommitted] = []
    bus.on(SceneObservationCommitted, observations.append)
    decide = AsyncMock(return_value=SceneDecision(transition="none"))
    controller = _controller(tmp_path, event_bus=bus, decision_provider=decide)

    controller.capture_passive_turn(
        BeforeTurnCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            content="你觉得这段技术方案合理吗？",
            timestamp=datetime.now(),
            retrieved_memory_block="",
            retrieval_trace_raw=None,
            history_messages=(),
        )
    )
    controller.schedule_passive_turn(
        AfterTurnCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            reply="我认为需要先验证边界条件。",
            tools_used=(),
            thinking=None,
            will_dispatch=False,
        )
    )
    await asyncio.gather(*controller.tasks.values())

    assert observations[0].transition == "none"
    assert observations[0].scene_key == ""
    assert observations[0].visual_description == ""
    assert controller.state.current("role:mira")["scene_key"] == ""
    await controller.terminate()


@pytest.mark.asyncio
async def test_invalid_scene_protocol_does_not_publish_observation(
    tmp_path: Path,
) -> None:
    bus = EventBus()
    observations: list[SceneObservationCommitted] = []
    bus.on(SceneObservationCommitted, observations.append)
    decide = AsyncMock(
        side_effect=SceneDecisionProtocolError(
            "场景观察必须调用一次提交工具",
            content_length=16,
        )
    )
    controller = _controller(tmp_path, event_bus=bus, decision_provider=decide)

    controller.capture_passive_turn(
        BeforeTurnCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            content="下雨了吗？",
            timestamp=datetime.now(),
            retrieved_memory_block="",
            retrieval_trace_raw=None,
            history_messages=(),
        )
    )
    controller.schedule_passive_turn(
        AfterTurnCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            reply="她站在雨里。",
            tools_used=(),
            thinking=None,
            will_dispatch=False,
        )
    )

    with pytest.raises(SceneDecisionProtocolError, match="必须调用一次"):
        await asyncio.gather(*controller.tasks.values())

    assert observations == []
    assert controller.state.current("role:mira")["scene_key"] == ""
    await controller.terminate()


@pytest.mark.asyncio
async def test_proactive_message_is_observed_with_shared_scene_state(
    tmp_path: Path,
) -> None:
    bus = EventBus()
    observations: list[SceneObservationCommitted] = []
    bus.on(SceneObservationCommitted, observations.append)
    decide = AsyncMock(
        return_value=SceneDecision(
            transition="changed",
            scene_key="rain-hug",
            visual_key="rain-hug-closeup",
            visual_description="粉发少女站在雨里",
        )
    )
    controller = _controller(tmp_path, event_bus=bus, decision_provider=decide)

    controller.schedule_proactive_turn(
        ProactiveMessageCommitted(
            session_key="role:mira",
            channel="desktop",
            role_id="mira",
            chat_id="role:mira",
            assistant_response="她忽然走近抱住了你。",
            thread_id="thread:mira:desktop",
            tools_used=("message_push",),
        )
    )
    await asyncio.gather(*controller.tasks.values())

    assert observations == [
        SceneObservationCommitted(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            role_id="mira",
            source="proactive",
            transition="changed",
            scene_key="rain-hug",
            visual_key="rain-hug-closeup",
            visual_description="粉发少女站在雨里",
            tools_used=("message_push",),
            role_name="Mira",
            role_description="粉发少女",
            assistant_reply="她忽然走近抱住了你。",
        )
    ]
    await controller.terminate()


def _run_passive_turn(
    controller: SceneAwarenessController,
    *,
    context_scope: Literal["user", "external"],
    history_messages: tuple[HistoryMessage, ...] = (),
) -> None:
    controller.capture_passive_turn(
        BeforeTurnCtx(
            session_key="role:mira",
            channel="qq",
            chat_id="group-1",
            content="看海吗？",
            timestamp=datetime.now(),
            retrieved_memory_block="",
            retrieval_trace_raw=None,
            history_messages=history_messages,
            context_scope=context_scope,
        )
    )
    controller.schedule_passive_turn(
        AfterTurnCtx(
            session_key="role:mira",
            channel="qq",
            chat_id="group-1",
            reply="她望向海边。",
            tools_used=(),
            thinking=None,
            will_dispatch=True,
        )
    )


def _proactive_event(thread_id: str) -> ProactiveMessageCommitted:
    return ProactiveMessageCommitted(
        session_key="role:mira",
        channel="desktop",
        role_id="mira",
        assistant_response="她看向你。",
        thread_id=thread_id,
    )


@pytest.mark.asyncio
async def test_external_context_passive_turn_is_not_observed(tmp_path: Path) -> None:
    decide = AsyncMock(return_value=SceneDecision("started", "sea", "sea", "海边"))
    controller = _controller(tmp_path, event_bus=EventBus(), decision_provider=decide)

    _run_passive_turn(controller, context_scope="external")
    await asyncio.gather(*controller.tasks.values())

    decide.assert_not_awaited()
    assert controller.state.is_current("role:mira", 0)
    await controller.terminate()


@pytest.mark.asyncio
async def test_user_context_passive_turn_sees_recent_history(tmp_path: Path) -> None:
    decide = AsyncMock(return_value=SceneDecision("started", "sea", "sea", "海边"))
    controller = _controller(tmp_path, event_bus=EventBus(), decision_provider=decide)

    _run_passive_turn(
        controller,
        context_scope="user",
        history_messages=(HistoryMessage(role="user", content="想去看海"),),
    )
    await asyncio.gather(*controller.tasks.values())

    assert decide.await_args.kwargs["decision_input"].recent_history == (
        {"role": "user", "content": "想去看海"},
    )
    await controller.terminate()


@pytest.mark.asyncio
async def test_external_context_proactive_message_is_not_observed(
    tmp_path: Path,
) -> None:
    decide = AsyncMock(return_value=SceneDecision("started", "sea", "sea", "海边"))
    controller = _controller(tmp_path, event_bus=EventBus(), decision_provider=decide)

    controller.schedule_proactive_turn(_proactive_event("thread:mira:qq:group-1"))
    await asyncio.gather(*controller.tasks.values())

    decide.assert_not_awaited()
    assert controller.state.is_current("role:mira", 0)
    await controller.terminate()


@pytest.mark.asyncio
async def test_user_context_proactive_message_only_sees_user_context(
    tmp_path: Path,
) -> None:
    decide = AsyncMock(return_value=SceneDecision("started", "sea", "sea", "海边"))
    controller = _controller(tmp_path, event_bus=EventBus(), decision_provider=decide)
    session = controller._session_manager.get_or_create("role:mira")
    session.add_message("user", "桌面上说想去看海", thread_id="thread:mira:desktop")
    session.add_message("user", "群里在聊游戏", thread_id="thread:mira:qq:group-1")

    controller.schedule_proactive_turn(_proactive_event("thread:mira:desktop"))
    await asyncio.gather(*controller.tasks.values())

    assert decide.await_args.kwargs["decision_input"].recent_history == (
        {"role": "user", "content": "桌面上说想去看海"},
    )
    await controller.terminate()
