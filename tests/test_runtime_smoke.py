import asyncio
import json
import sys
import types
from pathlib import Path
from typing import cast, Any
from unittest.mock import AsyncMock

import pytest

import main
from bootstrap import app as bootstrap_app
from bootstrap import init_workspace as workspace_init
from bootstrap.channels import start_channels
from agent.config import (
    ChannelsConfig,
    Config,
    QQChannelConfig,
    TelegramChannelConfig,
    load_config,
)
from bus.event_bus import EventBus
from core.net.http import SharedHttpResources


def _toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    return str(value)


def _dump_toml(data: dict, prefix: tuple[str, ...] = ()) -> list[str]:
    lines: list[str] = []
    scalar_lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, dict):
            continue
        scalar_lines.append(f"{key} = {_toml_value(value)}")
    if prefix:
        lines.append(f"[{'.'.join(prefix)}]")
    lines.extend(scalar_lines)
    if scalar_lines:
        lines.append("")
    for key, value in data.items():
        if isinstance(value, dict):
            lines.extend(_dump_toml(value, prefix + (key,)))
    return lines


def _write_config(path: Path) -> None:
    payload = {
        "llm": {
            "provider": "openai",
            "main": {
                "model": "test-model",
                "api_key": "test-key",
            },
        },
        "agent": {
            "system_prompt": "test system prompt",
            "max_tokens": 256,
            "max_iterations": 2,
            "maintenance": {
                "memory_optimizer_enabled": False,
            },
        },
        "proactive": {
            "enabled": False,
            "profile": "quiet",
        },
    }
    path.write_text("\n".join(_dump_toml(payload)).strip() + "\n", encoding="utf-8")


def test_load_config_keeps_internal_max_iterations_default(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[llm]
provider = "openai"

[llm.main]
model = "test-model"
api_key = "test-key"

[agent]
system_prompt = "test"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    cfg = load_config(config_path)

    assert cfg.max_iterations == 10


def test_load_config_defaults_memory_window_and_optimizer_interval(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[llm]
provider = "openai"

[llm.main]
model = "test-model"
api_key = "test-key"

[agent]
system_prompt = "test"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    cfg = load_config(config_path)

    assert cfg.memory_window == 40
    assert cfg.memory_optimizer_interval_seconds == 64800


@pytest.mark.asyncio
async def test_run_cleanup_steps_continues_after_failure():
    calls: list[str] = []

    async def _fail() -> None:
        calls.append("fail")
        raise RuntimeError("stop failed")

    async def _cleanup() -> None:
        calls.append("cleanup")

    with pytest.raises(RuntimeError, match="stop failed"):
        await bootstrap_app._run_cleanup_steps(
            ("fail", _fail),
            ("cleanup", _cleanup),
        )

    assert calls == ["fail", "cleanup"]

def test_init_workspace_creates_expected_assets(tmp_path):
    config_path = tmp_path / "config.toml"
    workspace = tmp_path / "workspace"

    summary = workspace_init.init_workspace(
        config_path=config_path,
        workspace=workspace,
    )

    assert config_path.exists()
    config_text = config_path.read_text(encoding="utf-8")
    assert "multimodal = false" in config_text
    assert "[llm.vl]" in config_text
    assert 'model = "qwen-vl-plus"' in config_text
    assert (workspace / "sessions.db").exists()
    assert (workspace / "observe").is_dir()
    assert (workspace / "memory" / "consolidation_writes.db").exists()
    assert (workspace / "memory" / "journal").is_dir()
    assert (workspace / "memory" / "memory2.db").exists()
    assert json.loads(
        (workspace / "mcp_servers.json").read_text(encoding="utf-8")
    ) == {"servers": {}}
    assert json.loads(
        (workspace / "proactive_sources.json").read_text(encoding="utf-8")
    ) == {"sources": []}
    assert (workspace / "skills").is_dir()
    assert not (workspace / "drift" / "skills").exists()
    assert (workspace / "roles" / "roles.json").exists()
    assert (workspace / "roles" / "assets").is_dir()
    assert any(path == config_path for path in summary.created)


def test_init_workspace_respects_force_for_text_assets(tmp_path):
    config_path = tmp_path / "config.toml"
    workspace = tmp_path / "workspace"

    workspace_init.init_workspace(
        config_path=config_path,
        workspace=workspace,
    )
    config_text = config_path.read_text(encoding="utf-8").replace(
        'model = "deepseek-v4-flash"',
        'model = "custom"',
        1,
    )
    config_path.write_text(config_text, encoding="utf-8")

    summary_skip = workspace_init.init_workspace(
        config_path=config_path,
        workspace=workspace,
    )
    assert 'model = "custom"' in config_path.read_text(encoding="utf-8")
    assert any(path == config_path for path in summary_skip.skipped)

    summary_force = workspace_init.init_workspace(
        config_path=config_path,
        workspace=workspace,
        force=True,
    )
    assert "[llm]" in config_path.read_text(encoding="utf-8")
    assert any(path == config_path for path in summary_force.overwritten)


@pytest.mark.asyncio
async def test_start_channels_wires_telegram_and_qq(monkeypatch, tmp_path):
    starts: list[str] = []
    registrations: list[tuple[str, list[str]]] = []

    fake_telegram_channel = types.ModuleType("infra.channels.telegram_channel")
    fake_qq_channel = types.ModuleType("infra.channels.qq_channel")

    class _TelegramChannel:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.name = kwargs.get("channel_name", "telegram")

        async def start(self, ctx) -> None:
            starts.append("telegram")
            ctx.push_tool.register_channel(
                self.name,
                text=self.send,
                stream_text=self.send_stream,
                file=self.send_file,
                image=self.send_image,
            )

        async def stop(self) -> None:
            starts.append("telegram.stop")

        async def send(self, *args, **kwargs):
            return None

        async def send_stream(self, *args, **kwargs):
            return None

        async def send_file(self, *args, **kwargs):
            return None

        async def send_image(self, *args, **kwargs):
            return None

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

    fake_telegram_channel.TelegramChannel = _TelegramChannel  # type: ignore[attr-defined]
    fake_qq_channel.QQChannel = _QQChannel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "infra.channels.telegram_channel", fake_telegram_channel)
    monkeypatch.setitem(sys.modules, "infra.channels.qq_channel", fake_qq_channel)

    class _PushTool:
        def register_channel(self, name: str, **kwargs) -> None:
            registrations.append((name, sorted(kwargs)))

    config = Config(
        provider="openai",
        model="m",
        api_key="k",
        system_prompt="s",
        channels=ChannelsConfig(
            telegram=TelegramChannelConfig(token="tg-token"),
            qq=QQChannelConfig(bot_uin="10001"),
        ),
    )
    resources = SharedHttpResources()
    event_bus = EventBus()
    try:
        controller = object()
        plugin_channel = _QQBotChannel(event_bus=event_bus)
        session_manager = types.SimpleNamespace(workspace=tmp_path)
        ipc, host = await start_channels(
            config,
            bus=cast(Any, object()),
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

    assert ipc is None
    tg, qq, qqbot = host.channels
    assert starts == ["telegram", "qq", "qqbot"]
    assert registrations == [
        ("telegram", ["file", "image", "stream_text", "text"]),
        ("qq", ["file", "image", "text"]),
        ("qqbot", ["stream_text", "text"]),
    ]
    assert tg.kwargs["event_bus"] is event_bus
    assert tg.kwargs["interrupt_controller"] is controller
    assert tg.kwargs["channel_hub"] is qq.kwargs["channel_hub"]
    assert tg.kwargs["channel_hub"] is not None
    assert qq.kwargs["interrupt_controller"] is controller
    assert qqbot.kwargs["event_bus"] is event_bus
    assert qqbot.context_hub is tg.kwargs["channel_hub"]


@pytest.mark.asyncio
async def test_start_channels_skips_unfilled_optional_channels(monkeypatch, tmp_path):
    starts: list[str] = []

    fake_telegram_channel = types.ModuleType("infra.channels.telegram_channel")
    fake_qq_channel = types.ModuleType("infra.channels.qq_channel")

    class _TelegramChannel:
        async def start(self) -> None:
            starts.append("telegram")

    class _QQChannel:
        async def start(self) -> None:
            starts.append("qq")

    fake_telegram_channel.TelegramChannel = _TelegramChannel  # type: ignore[attr-defined]
    fake_qq_channel.QQChannel = _QQChannel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "infra.channels.telegram_channel", fake_telegram_channel)
    monkeypatch.setitem(sys.modules, "infra.channels.qq_channel", fake_qq_channel)

    class _PushTool:
        def register_channel(self, name: str, **kwargs) -> None:
            raise AssertionError(f"unexpected channel registration: {name}")

    config = Config(
        provider="openai",
        model="m",
        api_key="k",
        system_prompt="s",
        channels=ChannelsConfig(
            telegram=None,
            qq=None,
        ),
    )
    resources = SharedHttpResources()
    try:
        ipc, host = await start_channels(
            config,
            bus=cast(Any, object()),
            session_manager=cast(Any, object()),
            push_tool=cast(Any, _PushTool()),
            http_resources=resources,
            event_bus=EventBus(),
        )
    finally:
        await resources.aclose()

    assert ipc is None
    assert host.channels == []
    assert starts == []


@pytest.mark.asyncio
async def test_start_channels_skips_channel_constructor_failures(monkeypatch):
    fake_telegram_channel = types.ModuleType("infra.channels.telegram_channel")
    fake_qq_channel = types.ModuleType("infra.channels.qq_channel")

    class _TelegramChannel:
        def __init__(self, **kwargs):
            raise ValueError("invalid telegram configuration")

    class _QQChannel:
        name = "qq"

        def __init__(self, **kwargs):
            pass

    fake_telegram_channel.TelegramChannel = _TelegramChannel  # type: ignore[attr-defined]
    fake_qq_channel.QQChannel = _QQChannel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "infra.channels.telegram_channel", fake_telegram_channel)
    monkeypatch.setitem(sys.modules, "infra.channels.qq_channel", fake_qq_channel)

    config = Config(
        provider="openai",
        model="m",
        api_key="k",
        system_prompt="s",
        channels=ChannelsConfig(
            telegram=TelegramChannelConfig(token="tg-token"),
            qq=QQChannelConfig(bot_uin="10001"),
        ),
    )
    resources = SharedHttpResources()
    try:
        _, host = await start_channels(
            config,
            bus=cast(Any, object()),
            session_manager=cast(Any, object()),
            push_tool=cast(Any, object()),
            http_resources=resources,
            event_bus=EventBus(),
        )
    finally:
        await resources.aclose()

    assert [channel.name for channel in host.channels] == ["qq"]


@pytest.mark.asyncio
async def test_start_channels_desktop_mode_skips_ipc_and_message_channels(
    monkeypatch,
    tmp_path,
):
    starts: list[str] = []

    fake_telegram_channel = types.ModuleType("infra.channels.telegram_channel")
    fake_qq_channel = types.ModuleType("infra.channels.qq_channel")

    class _TelegramChannel:
        def __init__(self, **kwargs):
            starts.append("telegram.init")

    class _QQChannel:
        def __init__(self, **kwargs):
            starts.append("qq.init")

    fake_telegram_channel.TelegramChannel = _TelegramChannel  # type: ignore[attr-defined]
    fake_qq_channel.QQChannel = _QQChannel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "infra.channels.telegram_channel", fake_telegram_channel)
    monkeypatch.setitem(sys.modules, "infra.channels.qq_channel", fake_qq_channel)

    config = Config(
        provider="openai",
        model="m",
        api_key="k",
        system_prompt="s",
        channels=ChannelsConfig(
            telegram=TelegramChannelConfig(token="tg-token"),
            qq=QQChannelConfig(bot_uin="10001"),
        ),
    )
    resources = SharedHttpResources()
    try:
        ipc, host = await start_channels(
            config,
            bus=cast(Any, object()),
            session_manager=cast(Any, object()),
            push_tool=cast(Any, object()),
            http_resources=resources,
            event_bus=EventBus(),
            enable_message_channels=False,
        )
    finally:
        await resources.aclose()

    assert ipc is None
    assert host.channels == []
    assert starts == []
