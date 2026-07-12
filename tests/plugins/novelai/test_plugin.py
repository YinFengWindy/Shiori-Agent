from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from agent.lifecycle.types import AfterReasoningCtx, AfterToolResultCtx
from agent.plugins.context import PluginContext, PluginKVStore
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from core.integrations.novelai.models import NovelAISettings
from plugins.novelai.plugin import NovelAIPlugin


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
