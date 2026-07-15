from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from agent.lifecycle.types import (
    AfterReasoningCtx,
    AfterToolResultCtx,
    AfterTurnCtx,
    BeforeTurnCtx,
)
from agent.plugins.context import PluginContext, PluginKVStore
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from core.integrations.novelai.models import NovelAISettings
from core.roles.store import RoleStore
from plugins.novelai.plugin import NovelAIPlugin
from plugins.novelai.scene_decision import SceneCgDecision


@pytest.mark.asyncio
async def test_plugin_registers_tool_and_attaches_generated_media(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "plugins.novelai.plugin.get_default_http_requester",
        lambda profile: SimpleNamespace(),
    )
    plugin = NovelAIPlugin()
    plugin.context = PluginContext(
        event_bus=EventBus(),
        tool_registry=ToolRegistry(),
        plugin_id="novelai",
        plugin_dir=tmp_path,
        kv_store=PluginKVStore(tmp_path / ".kv.json"),
        app_config=SimpleNamespace(
            novelai=NovelAISettings(enabled=True, token="novel-token")
        ),
        workspace=tmp_path,
    )

    await plugin.initialize()
    assert plugin.context.tool_registry.has_tool("generate_image") is True

    await plugin.collect_generated_media(
        AfterToolResultCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="desktop",
            tool_name="generate_image",
            arguments={},
            result=json.dumps({"output_paths": [str(tmp_path / "output.png")]}),
            status="success",
        )
    )
    ctx = AfterReasoningCtx(
        session_key="role:mira",
        channel="desktop",
        chat_id="desktop",
        tools_used=(),
        thinking=None,
        response_metadata=cast(Any, SimpleNamespace(raw_text="ok")),
        streamed=False,
        tool_chain=(),
        context_retry={},
        reply="已生成",
    )

    updated = await plugin.attach_generated_media(ctx)

    assert updated.media == [str(tmp_path / "output.png")]
    await plugin.terminate()
    assert plugin.context.tool_registry.has_tool("generate_image") is False


@pytest.mark.asyncio
async def test_plugin_does_not_attach_media_already_sent_by_message_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "plugins.novelai.plugin.get_default_http_requester",
        lambda profile: SimpleNamespace(),
    )
    plugin = NovelAIPlugin()
    plugin.context = PluginContext(
        event_bus=EventBus(),
        tool_registry=ToolRegistry(),
        plugin_id="novelai",
        plugin_dir=tmp_path,
        kv_store=PluginKVStore(tmp_path / ".kv.json"),
        app_config=SimpleNamespace(
            novelai=NovelAISettings(enabled=True, token="novel-token")
        ),
        workspace=tmp_path,
    )
    await plugin.initialize()
    image = str(tmp_path / "output.png")

    await plugin.collect_generated_media(
        AfterToolResultCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="desktop",
            tool_name="generate_image",
            arguments={},
            result=json.dumps({"output_paths": [image]}),
            status="success",
        )
    )
    await plugin.consume_pushed_media(
        AfterToolResultCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="desktop",
            tool_name="message_push",
            arguments={"image": image},
            result="图片已发送",
            status="success",
        )
    )

    ctx = AfterReasoningCtx(
        session_key="role:mira",
        channel="desktop",
        chat_id="desktop",
        tools_used=(),
        thinking=None,
        response_metadata=cast(Any, SimpleNamespace(raw_text="ok")),
        streamed=False,
        tool_chain=(),
        context_retry={},
        reply="已发送",
    )
    updated = await plugin.attach_generated_media(ctx)

    assert updated.media == []
    await plugin.terminate()


def _plugin_context(
    tmp_path: Path,
    *,
    tool_registry: ToolRegistry | None = None,
    light_provider: object | None = None,
    session_manager: object | None = None,
) -> PluginContext:
    return PluginContext(
        event_bus=EventBus(),
        tool_registry=tool_registry or ToolRegistry(),
        plugin_id="novelai",
        plugin_dir=tmp_path,
        kv_store=PluginKVStore(tmp_path / ".kv.json"),
        app_config=SimpleNamespace(
            novelai=NovelAISettings(enabled=True, token="novel-token")
        ),
        light_provider=light_provider,
        light_model="qwen-flash" if light_provider is not None else "",
        workspace=tmp_path,
        session_manager=session_manager,
    )


@pytest.mark.asyncio
async def test_plugin_runs_auto_cg_in_background_and_pushes_generated_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "plugins.novelai.plugin.get_default_http_requester",
        lambda profile: SimpleNamespace(),
    )
    _ = RoleStore(tmp_path).create_role(
        role_id="mira",
        name="Mira",
        system_prompt="粉色长发少女",
        runtime_config={"auto_scene_cg_enabled": True},
    )
    session = SimpleNamespace(metadata={"role_id": "mira"})
    session_manager = SimpleNamespace(get_or_create=lambda session_key: session)
    registry = ToolRegistry()
    push_image = AsyncMock()
    push_tool = MessagePushTool()
    push_tool.register_channel("desktop", image=push_image)
    registry.register(push_tool)
    light_provider = SimpleNamespace(chat=AsyncMock())
    decision = AsyncMock(
        return_value=SceneCgDecision(
            should_generate=True,
            scene_key="rain-confession",
            prompt="1girl, pink hair, standing in rain, emotional, night",
            negative_prompt="blurry, text",
            size_preset="portrait",
        )
    )
    monkeypatch.setattr("plugins.novelai.plugin.decide_scene_cg", decision)
    plugin = NovelAIPlugin()
    plugin.context = _plugin_context(
        tmp_path,
        tool_registry=registry,
        light_provider=light_provider,
        session_manager=session_manager,
    )
    await plugin.initialize()
    image_path = str(tmp_path / "cg.png")
    generate = AsyncMock(return_value=json.dumps({"output_paths": [image_path]}))
    monkeypatch.setattr(plugin._tool, "execute", generate)

    await plugin.advance_auto_cg_turn(
        BeforeTurnCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="chat",
            content="我终于找到你了",
            timestamp=datetime.now(),
            retrieved_memory_block="",
            retrieval_trace_raw=None,
            history_messages=({"role": "assistant", "content": "雨越来越大了。"},),
        )
    )
    await plugin.schedule_auto_cg(
        AfterTurnCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="chat",
            reply="她站在雨里，终于说出了藏了很久的话。",
            tools_used=(),
            thinking=None,
            will_dispatch=True,
        )
    )
    decision.assert_not_awaited()

    tasks = list(plugin._auto_cg_tasks.values())
    assert len(tasks) == 1
    await asyncio.gather(*tasks)
    await asyncio.sleep(0)

    completed_input = decision.await_args.kwargs["decision_input"]
    assert completed_input.assistant_reply == "她站在雨里，终于说出了藏了很久的话。"
    generated_arguments = generate.await_args.kwargs
    assert generated_arguments["intent"] == "scene_cg"
    assert generated_arguments["scene_key"] == "rain-confession"
    assert "third-person view" in generated_arguments["prompt"]
    push_image.assert_awaited_once_with("chat", image_path)
    state = plugin.context.kv_store.get("auto_cg_sessions")
    assert state["role:mira"]["last_scene_key"] == "rain-confession"
    await plugin.terminate()


@pytest.mark.asyncio
async def test_plugin_skips_auto_cg_after_manual_generation_and_during_cooldown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "plugins.novelai.plugin.get_default_http_requester",
        lambda profile: SimpleNamespace(),
    )
    _ = RoleStore(tmp_path).create_role(
        role_id="mira",
        name="Mira",
        system_prompt="role",
        runtime_config={"auto_scene_cg_enabled": True},
    )
    session = SimpleNamespace(metadata={"role_id": "mira"})
    light_provider = SimpleNamespace(chat=AsyncMock())
    decision = AsyncMock(return_value=SceneCgDecision(should_generate=False))
    monkeypatch.setattr("plugins.novelai.plugin.decide_scene_cg", decision)
    plugin = NovelAIPlugin()
    plugin.context = _plugin_context(
        tmp_path,
        light_provider=light_provider,
        session_manager=SimpleNamespace(get_or_create=lambda session_key: session),
    )
    await plugin.initialize()

    before_turn = BeforeTurnCtx(
        session_key="role:mira",
        channel="desktop",
        chat_id="chat",
        content="message",
        timestamp=datetime.now(),
        retrieved_memory_block="",
        retrieval_trace_raw=None,
        history_messages=(),
    )
    await plugin.advance_auto_cg_turn(before_turn)
    await plugin.schedule_auto_cg(
        AfterTurnCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="chat",
            reply="reply",
            tools_used=("generate_image",),
            thinking=None,
            will_dispatch=True,
        )
    )
    await asyncio.gather(*plugin._auto_cg_tasks.values())
    assert plugin._auto_cg_tasks == {}

    await plugin.advance_auto_cg_turn(before_turn)
    plugin._auto_cg.record_success("role:mira", "current-scene")
    await plugin.schedule_auto_cg(
        AfterTurnCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="chat",
            reply="reply",
            tools_used=(),
            thinking=None,
            will_dispatch=True,
        )
    )
    await asyncio.gather(*plugin._auto_cg_tasks.values())
    assert plugin._auto_cg_tasks == {}
    assert decision.await_count == 2
    await plugin.terminate()


@pytest.mark.asyncio
async def test_plugin_allows_only_one_auto_cg_task_and_cancels_it_on_terminate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "plugins.novelai.plugin.get_default_http_requester",
        lambda profile: SimpleNamespace(),
    )
    _ = RoleStore(tmp_path).create_role(
        role_id="mira",
        name="Mira",
        system_prompt="role",
        runtime_config={"auto_scene_cg_enabled": True},
    )
    session = SimpleNamespace(metadata={"role_id": "mira"})
    started = asyncio.Event()
    blocker = asyncio.Event()

    async def wait_for_decision(*args: object, **kwargs: object) -> SceneCgDecision:
        started.set()
        await blocker.wait()
        return SceneCgDecision(should_generate=False)

    monkeypatch.setattr("plugins.novelai.plugin.decide_scene_cg", wait_for_decision)
    plugin = NovelAIPlugin()
    plugin.context = _plugin_context(
        tmp_path,
        light_provider=SimpleNamespace(chat=AsyncMock()),
        session_manager=SimpleNamespace(get_or_create=lambda session_key: session),
    )
    await plugin.initialize()
    before_turn = BeforeTurnCtx(
        session_key="role:mira",
        channel="desktop",
        chat_id="chat",
        content="message",
        timestamp=datetime.now(),
        retrieved_memory_block="",
        retrieval_trace_raw=None,
        history_messages=(),
    )
    after_turn = AfterTurnCtx(
        session_key="role:mira",
        channel="desktop",
        chat_id="chat",
        reply="reply",
        tools_used=(),
        thinking=None,
        will_dispatch=True,
    )

    await plugin.advance_auto_cg_turn(before_turn)
    await plugin.schedule_auto_cg(after_turn)
    await started.wait()
    task = plugin._auto_cg_tasks["role:mira"]
    await plugin.advance_auto_cg_turn(before_turn)
    await plugin.schedule_auto_cg(after_turn)

    assert list(plugin._auto_cg_tasks.values()) == [task]
    await plugin.terminate()
    assert task.cancelled()


@pytest.mark.asyncio
async def test_plugin_records_auto_cg_state_only_after_successful_media(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "plugins.novelai.plugin.get_default_http_requester",
        lambda profile: SimpleNamespace(),
    )
    plugin = NovelAIPlugin()
    plugin.context = _plugin_context(tmp_path)
    await plugin.initialize()
    arguments = {"intent": "scene_cg", "scene_key": "rain"}

    await plugin.collect_generated_media(
        AfterToolResultCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="desktop",
            tool_name="generate_image",
            arguments=arguments,
            result="upstream error",
            status="error",
        )
    )
    assert plugin.context.kv_store.get("auto_cg_sessions") is None

    await plugin.collect_generated_media(
        AfterToolResultCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="desktop",
            tool_name="generate_image",
            arguments=arguments,
            result=json.dumps({"output_paths": [str(tmp_path / "cg.png")]}),
            status="success",
        )
    )
    sessions = plugin.context.kv_store.get("auto_cg_sessions")
    assert sessions["role:mira"]["last_scene_key"] == "rain"
    await plugin.terminate()
