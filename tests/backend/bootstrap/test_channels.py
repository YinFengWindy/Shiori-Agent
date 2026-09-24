from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest

from agent.config_models import Config
from agent.tools.message_push import MessagePushTool
from bootstrap.channels import start_channels
from bus.event_bus import EventBus
from bus.queue import MessageBus
from core.net.http import SharedHttpResources
from session.manager import SessionManager
from plugins.qqbot.backend.channel import QQBotChannel


@pytest.mark.asyncio
async def test_model_only_change_reuses_independently_owned_qqbot_connection(tmp_path):
    from dataclasses import replace

    config = Config(provider="", model="", api_key="")
    resources = SharedHttpResources()
    old = QQBotChannel("account-A", "secret-A")
    new = QQBotChannel("account-A", "secret-A")
    changed = QQBotChannel("account-B", "secret-B")
    context = dict(
        bus=MessageBus(),
        session_manager=SessionManager(tmp_path),
        push_tool=MessagePushTool(),
        http_resources=resources,
        event_bus=EventBus(),
    )
    try:
        active = await start_channels(config, plugin_channels=[old], **context)
        candidate = await start_channels(
            replace(config, max_tokens=2048),
            plugin_channels=[new],
            previous_host=active,
            **context,
        )
        assert candidate.channels == [old]
        assert not active.requires_exclusive_handover(candidate)
        assert new._client.is_closed
        replacement = await start_channels(
            config, plugin_channels=[changed], previous_host=active, **context
        )
        assert replacement.channels == [changed]
        assert active.requires_exclusive_handover(replacement)
    finally:
        await old.stop()
        await new.stop()
        await changed.stop()
        await resources.aclose()


class _KeyedChannel:
    """Plugin channel stub with a reuse key; optionally consumes bot commands."""

    name = "fake"
    configuration_key = ("fake", "token")

    def __init__(self, *, uses_bot_commands: bool) -> None:
        if uses_bot_commands:
            self.uses_bot_commands = True
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.pause_intake = Mock()
        self.resume_intake = Mock()


@pytest.mark.asyncio
@pytest.mark.parametrize("uses_bot_commands", [True, False])
async def test_bot_command_changes_rebuild_only_channels_that_use_them(
    tmp_path, uses_bot_commands
):
    """命令列表变化只重建声明 uses_bot_commands 的渠道（如 Telegram）；其余复用。"""
    config = Config(provider="", model="", api_key="")
    resources = SharedHttpResources()
    old, same, candidate = (
        _KeyedChannel(uses_bot_commands=uses_bot_commands) for _ in range(3)
    )
    context = dict(
        bus=MessageBus(),
        session_manager=SessionManager(tmp_path),
        push_tool=MessagePushTool(),
        http_resources=resources,
        event_bus=EventBus(),
    )
    commands = [("undo", "撤销上一轮对话")]
    try:
        active = await start_channels(
            config, plugin_channels=[cast(Any, old)], bot_commands=commands, **context
        )
        unchanged = await start_channels(
            config,
            plugin_channels=[cast(Any, same)],
            bot_commands=list(commands),
            previous_host=active,
            **context,
        )
        assert unchanged.channels == [old]
        changed = await start_channels(
            config,
            plugin_channels=[cast(Any, candidate)],
            bot_commands=[*commands, ("chatid", "查看我的 chat_id")],
            previous_host=active,
            **context,
        )
        if uses_bot_commands:
            assert changed.channels == [candidate]
            assert active.requires_exclusive_handover(changed)
        else:
            assert changed.channels == [old]
            candidate.stop.assert_awaited_once()
    finally:
        await resources.aclose()


class _PluginChannel:
    name = "fake"

    def __init__(self, starts: list[str]) -> None:
        self._starts = starts
        self.context = None

    async def start(self, ctx) -> None:
        self._starts.append("fake")
        self.context = ctx
        ctx.push_tool.register_channel(self.name, text=self.send)

    async def stop(self) -> None:
        self._starts.append("fake.stop")

    async def send(self, *args, **kwargs):
        return None


@pytest.mark.asyncio
async def test_start_channels_wires_plugin_channels_with_shared_context(tmp_path):
    starts: list[str] = []
    registrations: list[tuple[str, list[str]]] = []

    class _PushTool(MessagePushTool):
        def register_channel(self, name: str, **kwargs) -> None:
            registrations.append((name, sorted(kwargs)))

    resources = SharedHttpResources()
    event_bus = EventBus()
    try:
        controller = object()
        plugin_channel = _PluginChannel(starts)
        host = await start_channels(
            Config(provider="openai", model="m", api_key="k"),
            bus=MessageBus(),
            session_manager=cast(Any, SessionManager(tmp_path)),
            push_tool=cast(Any, _PushTool()),
            http_resources=resources,
            event_bus=event_bus,
            interrupt_controller=cast(Any, controller),
            plugin_channels=[cast(Any, plugin_channel)],
        )
        await host.start_all()
    finally:
        await resources.aclose()

    assert host.channels == [plugin_channel]
    assert starts == ["fake"]
    assert registrations == [("fake", ["text"])]
    context = plugin_channel.context
    assert context is not None
    assert context.event_bus is event_bus
    assert context.interrupt_controller is controller
    assert context.http_resources is resources
    assert context.channel_hub is not None


@pytest.mark.asyncio
async def test_start_channels_without_plugin_channels_starts_nothing(tmp_path):
    resources = SharedHttpResources()
    try:
        host = await start_channels(
            Config(provider="openai", model="m", api_key="k"),
            bus=MessageBus(),
            session_manager=SessionManager(tmp_path),
            push_tool=MessagePushTool(),
            http_resources=resources,
            event_bus=EventBus(),
        )
    finally:
        await resources.aclose()

    assert host.channels == []


@pytest.mark.asyncio
async def test_start_channels_desktop_mode_skips_message_channels(tmp_path):
    starts: list[str] = []
    resources = SharedHttpResources()
    try:
        host = await start_channels(
            Config(provider="openai", model="m", api_key="k"),
            bus=MessageBus(),
            session_manager=SessionManager(tmp_path),
            push_tool=MessagePushTool(),
            http_resources=resources,
            event_bus=EventBus(),
            plugin_channels=[cast(Any, _PluginChannel(starts))],
            enable_message_channels=False,
        )
        await host.start_all()
    finally:
        await resources.aclose()

    assert host.channels == []
    assert starts == []


@pytest.mark.asyncio
async def test_reused_connection_stops_the_unused_candidate(tmp_path):
    """同配置的插件渠道跨代复用旧连接，新构造的那份立即 stop，不产生流量。"""
    resources = SharedHttpResources()

    context = dict(
        bus=MessageBus(),
        session_manager=SessionManager(tmp_path),
        push_tool=MessagePushTool(),
        http_resources=resources,
        event_bus=EventBus(),
    )
    old = _KeyedChannel(uses_bot_commands=False)
    new = _KeyedChannel(uses_bot_commands=False)
    config = Config(provider="", model="", api_key="")
    try:
        active = await start_channels(
            config, plugin_channels=[cast(Any, old)], **context
        )
        await active.start_all()
        candidate = await start_channels(
            config,
            plugin_channels=[cast(Any, new)],
            previous_host=active,
            strict=True,
            **context,
        )
        assert candidate.channels == [old]
        new.stop.assert_awaited_once()
        await active.handover(candidate)
        old.start.assert_awaited_once()
        old.stop.assert_not_awaited()
        new.start.assert_not_awaited()
    finally:
        await resources.aclose()
