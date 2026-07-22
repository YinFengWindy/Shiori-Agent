from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from agent.lifecycle.types import AfterReasoningCtx, AfterToolResultCtx
from agent.plugins.context import PluginContext, PluginKVStore
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from bus.events_lifecycle import SceneObservationCommitted
from core.integrations.novelai.models import NovelAISettings
from core.roles.store import RoleStore
from plugins.novelai.plugin import NovelAIPlugin
from session.manager import SessionManager


def _plugin_context(
    tmp_path: Path,
    *,
    tool_registry: ToolRegistry | None = None,
    event_bus: EventBus | None = None,
    session_manager: object | None = None,
) -> PluginContext:
    return PluginContext(
        event_bus=event_bus or EventBus(),
        tool_registry=tool_registry or ToolRegistry(),
        plugin_id="novelai",
        plugin_dir=tmp_path,
        kv_store=PluginKVStore(tmp_path / ".kv.json"),
        app_config=SimpleNamespace(
            novelai=NovelAISettings(enabled=True, token="novel-token")
        ),
        workspace=tmp_path,
        session_manager=session_manager,
    )


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
    plugin.context = _plugin_context(tmp_path)

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
    updated = await plugin.attach_generated_media(
        AfterReasoningCtx(
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
    )

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
    plugin.context = _plugin_context(tmp_path)
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
    updated = await plugin.attach_generated_media(
        AfterReasoningCtx(
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
    )

    assert updated.media == []
    await plugin.terminate()


@pytest.mark.asyncio
async def test_plugin_generates_required_scene_cg_from_observation(
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
    sessions = SessionManager(tmp_path)
    sessions.open_role_session("mira", role_name="Mira")
    event_bus = EventBus()
    registry = ToolRegistry()
    push_image = AsyncMock()
    push_tool = MessagePushTool(event_bus=event_bus)
    push_tool.register_channel("telegram", image=push_image)
    registry.register(push_tool)
    plugin = NovelAIPlugin()
    plugin.context = _plugin_context(
        tmp_path,
        tool_registry=registry,
        event_bus=event_bus,
        session_manager=sessions,
    )
    await plugin.initialize()
    image_path = str(tmp_path / "cg.png")
    generate = AsyncMock(return_value=json.dumps({"output_paths": [image_path]}))
    monkeypatch.setattr(plugin._tool, "execute", generate)

    await event_bus.fanout(
        SceneObservationCommitted(
            session_key="role:mira",
            channel="telegram",
            chat_id="chat",
            role_id="mira",
            source="passive",
            transition="started",
            scene_key="rain-confession",
            visual_key="rain-confession-standing",
            should_generate=True,
            prompt="1girl, pink hair, standing in rain, emotional, night",
            negative_prompt="blurry, text",
            size_preset="portrait",
        )
    )
    await asyncio.gather(*plugin._auto_cg_tasks.values())

    generated_arguments = generate.await_args.kwargs
    assert generated_arguments["scene_key"] == "rain-confession"
    assert generated_arguments["visual_key"] == "rain-confession-standing"
    assert "third-person view" in generated_arguments["prompt"]
    push_image.assert_awaited_once_with("chat", image_path)
    state = plugin.context.kv_store.get("auto_cg_sessions")
    assert state["role:mira"]["last_visual_key"] == "rain-confession-standing"
    await plugin.terminate()


@pytest.mark.asyncio
async def test_required_scene_change_bypasses_cooldown(
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
    registry = ToolRegistry()
    push_tool = MessagePushTool()
    push_tool.register_channel("desktop", image=AsyncMock())
    registry.register(push_tool)
    plugin = NovelAIPlugin()
    plugin.context = _plugin_context(
        tmp_path,
        tool_registry=registry,
        session_manager=SimpleNamespace(get_or_create=lambda _key: session),
    )
    await plugin.initialize()
    plugin._auto_cg.advance_turn("role:mira")
    plugin._auto_cg.record_success("role:mira", "old-scene")
    generate = AsyncMock(return_value='{"output_paths":["changed.png"]}')
    monkeypatch.setattr(plugin._tool, "execute", generate)

    await plugin.context.event_bus.fanout(
        SceneObservationCommitted(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            role_id="mira",
            source="proactive",
            transition="changed",
            scene_key="new-scene",
            visual_key="new-scene-window",
            should_generate=True,
            prompt="1girl, sitting by window",
        )
    )
    await asyncio.gather(*plugin._auto_cg_tasks.values())

    generate.assert_awaited_once()
    await plugin.terminate()


@pytest.mark.asyncio
async def test_same_scene_respects_manual_generation_and_cooldown(
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
    plugin = NovelAIPlugin()
    plugin.context = _plugin_context(
        tmp_path,
        session_manager=SimpleNamespace(get_or_create=lambda _key: session),
    )
    await plugin.initialize()
    generate = AsyncMock(return_value='{"output_paths":["same.png"]}')
    monkeypatch.setattr(plugin._tool, "execute", generate)
    base = dict(
        session_key="role:mira",
        channel="desktop",
        chat_id="role:mira",
        role_id="mira",
        source="passive",
        transition="same",
        scene_key="same-scene",
        visual_key="same-scene-window",
        should_generate=True,
        prompt="1girl, sitting by window",
    )

    await plugin.context.event_bus.fanout(
        SceneObservationCommitted(**base, tools_used=("generate_image",))
    )
    plugin._auto_cg.record_success("role:mira", "old-scene")
    await plugin.context.event_bus.fanout(SceneObservationCommitted(**base))

    assert plugin._auto_cg_tasks == {}
    generate.assert_not_awaited()
    await plugin.terminate()


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
    arguments = {
        "intent": "scene_cg",
        "scene_key": "rain",
        "visual_key": "rain-standing",
    }

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
    assert sessions["role:mira"]["last_visual_key"] == "rain-standing"
    await plugin.terminate()
