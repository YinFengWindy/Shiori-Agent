from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from agent.lifecycle.types import AfterTurnCtx, BeforeTurnCtx
from agent.plugins.context import PluginKVStore
from bus.event_bus import EventBus
from bus.events_lifecycle import (
    ProactiveMessageCommitted,
    SceneObservationCommitted,
)
from core.roles.store import RoleStore
from plugins.scene_awareness.contracts import SceneDecisionProtocolError
from plugins.scene_awareness.controller import SceneAwarenessController
from plugins.scene_awareness.decision import SceneDecision
from session.manager import SessionManager


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
        runtime_config={"auto_scene_cg_enabled": True},
    )
    sessions = SessionManager(tmp_path)
    sessions.open_role_session("mira", role_name="Mira")
    return SceneAwarenessController(
        role_store=role_store,
        session_manager=sessions,
        event_bus=event_bus,
        kv_store=PluginKVStore(tmp_path / ".kv.json"),
        light_provider=cast(Any, object()),
        light_model="light-model",
        decision_provider=decision_provider,
    )


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
            should_generate=True,
            prompt="1girl, rain",
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
            should_generate=True,
            prompt="1girl, cooking in kitchen",
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
    assert observations[0].size_preset == ""
    assert controller._current_scene_key("role:mira") == ""
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
    assert controller._current_scene_key("role:mira") == ""
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
            should_generate=True,
            prompt="2girls, hugging, rain",
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
            should_generate=True,
            prompt="2girls, hugging, rain",
            tools_used=("message_push",),
        )
    ]
    await controller.terminate()
