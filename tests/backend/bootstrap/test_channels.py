import sys
import types
from types import ModuleType
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest

from agent.config_models import ChannelsConfig, Config, QQChannelConfig
from agent.tools.message_push import MessagePushTool
from bootstrap.channels import start_channels
from bus.event_bus import EventBus
from bus.queue import MessageBus
from core.net.http import SharedHttpResources
from session.manager import SessionManager
from plugins.qqbot.backend.channel import QQBotChannel


@pytest.mark.asyncio
async def test_preparation_reuses_unchanged_connection_without_starting_traffic(
    tmp_path, monkeypatch
):
    created = []

    class QQ:
        name = "qq"

        def __init__(self, **kwargs):
            self.start = AsyncMock()
            self.stop = AsyncMock()
            self.resume_intake = Mock()
            created.append(self)

    module = ModuleType("infra.channels.qq_channel")
    module.QQChannel = QQ
    monkeypatch.setitem(sys.modules, "infra.channels.qq_channel", module)
    config = Config(
        provider="",
        model="",
        api_key="",
        channels=ChannelsConfig(qq=QQChannelConfig(bot_uin="10001")),
    )
    resources = SharedHttpResources()
    context = dict(
        bus=MessageBus(),
        session_manager=SessionManager(tmp_path),
        push_tool=MessagePushTool(),
        http_resources=resources,
        event_bus=EventBus(),
    )
    try:
        active = await start_channels(config, **context)
        await active.start_all()
        candidate = await start_channels(
            config, previous_host=active, strict=True, **context
        )
        assert len(created) == 1
        assert candidate.channels == active.channels
        await active.handover(candidate)
        created[0].start.assert_awaited_once()
        created[0].stop.assert_not_awaited()
    finally:
        await resources.aclose()


@pytest.mark.asyncio
async def test_strict_preparation_surfaces_constructor_failure(tmp_path, monkeypatch):
    class QQ:
        def __init__(self, **kwargs):
            raise ValueError("bad token format")

    module = ModuleType("infra.channels.qq_channel")
    module.QQChannel = QQ
    monkeypatch.setitem(sys.modules, "infra.channels.qq_channel", module)
    config = Config(
        provider="",
        model="",
        api_key="",
        channels=ChannelsConfig(qq=QQChannelConfig(bot_uin="10001")),
    )
    resources = SharedHttpResources()
    try:
        with pytest.raises(ValueError, match="bad token format"):
            await start_channels(
                config,
                bus=MessageBus(),
                session_manager=SessionManager(tmp_path),
                push_tool=MessagePushTool(),
                http_resources=resources,
                event_bus=EventBus(),
                strict=True,
            )
    finally:
        await resources.aclose()


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


@pytest.mark.asyncio
async def test_changed_bot_commands_rebuild_plugin_connection(tmp_path):
    config = Config(provider="", model="", api_key="")
    resources = SharedHttpResources()
    old = QQBotChannel("account-A", "secret-A")
    same = QQBotChannel("account-A", "secret-A")
    rebuilt = QQBotChannel("account-A", "secret-A")
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
            config, plugin_channels=[old], bot_commands=commands, **context
        )
        unchanged = await start_channels(
            config,
            plugin_channels=[same],
            bot_commands=list(commands),
            previous_host=active,
            **context,
        )
        assert unchanged.channels == [old]
        changed = await start_channels(
            config,
            plugin_channels=[rebuilt],
            bot_commands=[*commands, ("chatid", "查看我的 chat_id")],
            previous_host=active,
            **context,
        )
        assert changed.channels == [rebuilt]
        assert active.requires_exclusive_handover(changed)
    finally:
        await old.stop()
        await same.stop()
        await rebuilt.stop()
        await resources.aclose()


@pytest.mark.asyncio
async def test_start_channels_wires_builtin_qq_and_plugin_channels(
    monkeypatch, tmp_path
):
    starts: list[str] = []
    registrations: list[tuple[str, list[str]]] = []

    fake_qq_channel = types.ModuleType("infra.channels.qq_channel")

    class _QQChannel:
        name = "qq"

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def start(self, ctx) -> None:
            starts.append("qq")
            ctx.push_tool.register_channel(
                self.name,
                text=self.send,
                file=self.send_file,
                image=self.send_image,
            )

        async def stop(self) -> None:
            starts.append("qq.stop")

        async def send(self, *args, **kwargs):
            return None

        async def send_file(self, *args, **kwargs):
            return None

        async def send_image(self, *args, **kwargs):
            return None

    class _QQBotChannel:
        name = "qqbot"

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.context_hub = None

        async def start(self, ctx) -> None:
            starts.append("qqbot")
            self.context_hub = ctx.channel_hub
            ctx.push_tool.register_channel(
                self.name,
                text=self.send_proactive,
                stream_text=self.send_stream,
            )

        async def stop(self) -> None:
            starts.append("qqbot.stop")

        async def send_proactive(self, *args, **kwargs):
            return None

        async def send_stream(self, *args, **kwargs):
            return None

    fake_qq_channel.QQChannel = _QQChannel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "infra.channels.qq_channel", fake_qq_channel)

    class _PushTool(MessagePushTool):
        def register_channel(self, name: str, **kwargs) -> None:
            registrations.append((name, sorted(kwargs)))

    config = Config(
        provider="openai",
        model="m",
        api_key="k",
        channels=ChannelsConfig(qq=QQChannelConfig(bot_uin="10001")),
    )
    resources = SharedHttpResources()
    event_bus = EventBus()
    try:
        controller = object()
        plugin_channel = _QQBotChannel(event_bus=event_bus)
        session_manager = types.SimpleNamespace(workspace=tmp_path)
        host = await start_channels(
            config,
            bus=MessageBus(),
            session_manager=cast(Any, session_manager),
            push_tool=cast(Any, _PushTool()),
            http_resources=resources,
            event_bus=event_bus,
            interrupt_controller=cast(Any, controller),
            plugin_channels=[cast(Any, plugin_channel)],
        )
        await host.start_all()
    finally:
        await resources.aclose()

    qq, qqbot = host.channels
    assert starts == ["qq", "qqbot"]
    assert registrations == [
        ("qq", ["file", "image", "text"]),
        ("qqbot", ["stream_text", "text"]),
    ]
    assert qq.kwargs["event_bus"] is event_bus
    assert qq.kwargs["interrupt_controller"] is controller
    assert qq.kwargs["channel_hub"] is not None
    assert qqbot.kwargs["event_bus"] is event_bus
    assert qqbot.context_hub is qq.kwargs["channel_hub"]


@pytest.mark.asyncio
async def test_start_channels_skips_unfilled_optional_channels(monkeypatch, tmp_path):
    starts: list[str] = []

    fake_qq_channel = types.ModuleType("infra.channels.qq_channel")

    class _QQChannel:
        async def start(self) -> None:
            starts.append("qq")

    fake_qq_channel.QQChannel = _QQChannel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "infra.channels.qq_channel", fake_qq_channel)

    class _PushTool(MessagePushTool):
        def register_channel(self, name: str, **kwargs) -> None:
            raise AssertionError(f"unexpected channel registration: {name}")

    config = Config(
        provider="openai",
        model="m",
        api_key="k",
        channels=ChannelsConfig(qq=None),
    )
    resources = SharedHttpResources()
    try:
        host = await start_channels(
            config,
            bus=MessageBus(),
            session_manager=cast(Any, object()),
            push_tool=cast(Any, _PushTool()),
            http_resources=resources,
            event_bus=EventBus(),
        )
    finally:
        await resources.aclose()

    assert host.channels == []
    assert starts == []


@pytest.mark.asyncio
async def test_start_channels_skips_channel_constructor_failures(monkeypatch):
    fake_qq_channel = types.ModuleType("infra.channels.qq_channel")

    class _QQChannel:
        def __init__(self, **kwargs):
            raise ValueError("invalid qq configuration")

    fake_qq_channel.QQChannel = _QQChannel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "infra.channels.qq_channel", fake_qq_channel)

    config = Config(
        provider="openai",
        model="m",
        api_key="k",
        channels=ChannelsConfig(qq=QQChannelConfig(bot_uin="10001")),
    )
    resources = SharedHttpResources()
    try:
        host = await start_channels(
            config,
            bus=MessageBus(),
            session_manager=cast(Any, object()),
            push_tool=MessagePushTool(),
            http_resources=resources,
            event_bus=EventBus(),
        )
    finally:
        await resources.aclose()

    assert host.channels == []
    assert [failure.channel for failure in host.failures] == ["qq"]


@pytest.mark.asyncio
async def test_start_channels_desktop_mode_skips_message_channels(
    monkeypatch,
    tmp_path,
):
    starts: list[str] = []

    fake_qq_channel = types.ModuleType("infra.channels.qq_channel")

    class _QQChannel:
        def __init__(self, **kwargs):
            starts.append("qq.init")

    fake_qq_channel.QQChannel = _QQChannel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "infra.channels.qq_channel", fake_qq_channel)

    config = Config(
        provider="openai",
        model="m",
        api_key="k",
        channels=ChannelsConfig(qq=QQChannelConfig(bot_uin="10001")),
    )
    resources = SharedHttpResources()
    try:
        host = await start_channels(
            config,
            bus=MessageBus(),
            session_manager=cast(Any, object()),
            push_tool=MessagePushTool(),
            http_resources=resources,
            event_bus=EventBus(),
            enable_message_channels=False,
        )
    finally:
        await resources.aclose()

    assert host.channels == []
    assert starts == []
