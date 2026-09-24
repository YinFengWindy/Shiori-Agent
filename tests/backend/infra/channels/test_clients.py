from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from bus.event_bus import EventBus
from bus.events import InboundMessage, OutboundMessage
from bus.events_lifecycle import (
    ToolCallCompleted,
    ToolCallStarted,
    TurnStarted,
)
from core.common.channel_directory import ChannelDirectory
from core.roles import RoleStore
from conversation.service import LegacySessionDescriptor
from infra.channels.base import AttachmentStore


class _Bus:
    def __init__(self) -> None:
        self.inbound = []
        self.outbound = []

    async def publish_inbound(self, msg) -> None:
        self.inbound.append(msg)

    def subscribe_outbound(self, channel, callback) -> None:
        self.outbound.append((channel, callback))

    def unsubscribe_outbound(self, channel, callback) -> None:
        self.outbound = [item for item in self.outbound if item != (channel, callback)]


class _SessionManager:
    def __init__(self, workspace: Path | None = None) -> None:
        self.sessions = {}
        self.saved = []
        self.delivery_updates = []
        self.workspace = workspace

    def get_or_create(self, key: str):
        return self.sessions.setdefault(key, SimpleNamespace(key=key, metadata={}))

    async def save_async(self, session) -> None:
        self.saved.append(session.key)

    def get_channel_metadata(self, channel: str):
        return []

    def role_session_key(self, role_id: str) -> str:
        return f"role:{role_id}"

    def sync_role_session_metadata(
        self,
        role_id: str,
        *,
        role_name: str,
        role_prompt: str,
        role_runtime_config: dict[str, Any],
        valid_illustrations: list[str],
    ):
        session = self.get_or_create(self.role_session_key(role_id))
        session.metadata.update(
            {
                "role_id": role_id,
                "role_name": role_name,
                "role_prompt": role_prompt,
                "role_runtime_config": role_runtime_config,
                "valid_illustrations": valid_illustrations,
            }
        )
        return session

    def mark_message_delivery(
        self,
        session_key: str,
        *,
        message_id: str,
        thread_id: str = "",
        delivery_status: str,
        external_message_id: str = "",
    ):
        payload = {
            "session_key": session_key,
            "message_id": message_id,
            "thread_id": thread_id,
            "delivery_status": delivery_status,
            "external_message_id": external_message_id,
        }
        self.delivery_updates.append(payload)
        return payload


def _import_qq_channel(monkeypatch: pytest.MonkeyPatch):
    ncatbot_core = types.ModuleType("ncatbot.core")
    ncatbot_core_adapter = types.ModuleType("ncatbot.core.adapter")
    ncatbot_core_adapter_adapter = types.ModuleType("ncatbot.core.adapter.adapter")
    ncatbot_utils = types.ModuleType("ncatbot.utils")
    captured_connect_calls = []

    class _Api:
        def __init__(self):
            self.calls = []

        async def send_group_text(self, group_id, content):
            self.calls.append(("group_text", group_id, content))

        async def send_private_text(self, user_id, content):
            self.calls.append(("private_text", user_id, content))

        async def send_group_file(self, group_id, uri, name):
            self.calls.append(("group_file", group_id, uri, name))

        async def send_private_file(self, user_id, uri, name):
            self.calls.append(("private_file", user_id, uri, name))

        async def send_group_image(self, group_id, image):
            self.calls.append(("group_image", group_id, image))

        async def send_private_image(self, user_id, image):
            self.calls.append(("private_image", user_id, image))

    class BotClient:
        def __init__(self):
            self.api = _Api()
            self.adapter = SimpleNamespace(connect_websocket=AsyncMock())
            self.private_handler = None
            self.group_handler = None
            self.startup_handler = None

        def on_private_message(self):
            def _wrap(fn):
                self.private_handler = fn
                return fn

            return _wrap

        def on_group_message(self):
            def _wrap(fn):
                self.group_handler = fn
                return fn

            return _wrap

        def on_startup(self):
            def _wrap(fn):
                self.startup_handler = fn
                return fn

            return _wrap

        def run_backend(self):
            return self.api

        def bot_exit(self):
            return None

    class ForwardConstructor:
        def __init__(self, user_id, nickname):
            self.user_id = user_id
            self.nickname = nickname
            self.nodes = []

        def attach_text(self, text, nickname=None):
            self.nodes.append(
                {
                    "type": "text",
                    "data": {"text": text},
                    "nickname": nickname or self.nickname,
                    "user_id": self.user_id,
                }
            )

        def to_forward(self):
            class _Forward:
                def __init__(self, nodes):
                    self._nodes = nodes

                def to_forward_dict(self):
                    return {
                        "messages": list(self._nodes),
                        "news": [],
                        "prompt": "",
                        "summary": "",
                        "source": "",
                    }

            return _Forward(self.nodes)

    def _fake_connect(*args, **kwargs):
        captured_connect_calls.append(kwargs.copy())
        return ("connect", args, kwargs)

    ncatbot_core.BotClient = BotClient
    ncatbot_core.ForwardConstructor = ForwardConstructor
    ncatbot_core_adapter_adapter.websockets = SimpleNamespace(connect=_fake_connect)
    ncatbot_core_adapter_adapter._captured_connect_calls = captured_connect_calls
    ncatbot_utils.ncatbot_config = SimpleNamespace(
        bt_uin="",
        root="",
        check_ncatbot_update=True,
        skip_ncatbot_install_check=False,
        napcat=SimpleNamespace(remote_mode=False, enable_webui=True),
        enable_webui_interaction=True,
        plugin=SimpleNamespace(plugins_dir=""),
    )
    monkeypatch.setitem(sys.modules, "ncatbot.core", ncatbot_core)
    monkeypatch.setitem(sys.modules, "ncatbot.core.adapter", ncatbot_core_adapter)
    monkeypatch.setitem(
        sys.modules,
        "ncatbot.core.adapter.adapter",
        ncatbot_core_adapter_adapter,
    )
    monkeypatch.setitem(sys.modules, "ncatbot.utils", ncatbot_utils)
    sys.modules.pop("infra.channels.qq_channel", None)
    return importlib.import_module("infra.channels.qq_channel")


def test_qq_channel_ws_timeout_patch_is_best_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _import_qq_channel(monkeypatch)
    adapter_mod = sys.modules["ncatbot.core.adapter.adapter"]
    original_connect = adapter_mod.websockets.connect

    from infra.channels.qq_channel.compat import patch_ncatbot_ws_open_timeout

    patch_ncatbot_ws_open_timeout(7.5)

    assert adapter_mod.websockets.connect is not original_connect
    adapter_mod.websockets.connect("ws://example.invalid", open_timeout=1)
    assert adapter_mod._captured_connect_calls[-1]["open_timeout"] == 7.5

    monkeypatch.delitem(sys.modules, "ncatbot.core.adapter.adapter", raising=False)
    # The optional SDK adapter may be absent in a clean installation.
    patch_ncatbot_ws_open_timeout(7.5)


@pytest.mark.asyncio
async def test_qq_channel_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    mod = _import_qq_channel(monkeypatch)
    ncatbot_dir = tmp_path / ".shiori" / "ncatbot"
    lifecycle = importlib.import_module("infra.channels.qq_channel.lifecycle")
    monkeypatch.setattr(lifecycle, "resolve_ncatbot_dir", lambda: ncatbot_dir)
    bus = _Bus()
    session_manager = _SessionManager(tmp_path)
    role_store = RoleStore(tmp_path)
    role_store.create_role(
        role_id="mira",
        name="Mira",
        description="bound qq role",
        system_prompt="you are mira",
    )
    role_store.update_role(
        "mira",
        channel_bindings=[
            {"channel": "qq", "chat_id": "1", "allow_from": ["1"]},
            {"channel": "qq", "chat_id": "gqq:100", "allow_from": ["1"]},
        ],
    )

    async def _request_get(url, **kwargs):
        if url.endswith("a.jpg") or url.endswith("a.png"):
            return SimpleNamespace(
                headers={"content-type": "image/png"},
                content=b"img",
                raise_for_status=lambda: None,
            )
        raise RuntimeError("boom")

    requester = SimpleNamespace(get=AsyncMock(side_effect=_request_get))
    group_filter = SimpleNamespace(should_process=AsyncMock(return_value=True))
    group_cfg = SimpleNamespace(group_id="100")
    channel = mod.QQChannel(
        "42",
        bus,
        session_manager,
        allow_from=["1"],
        groups=[group_cfg],
        websocket_open_timeout_seconds=7.5,
        group_filter=group_filter,
        http_requester=requester,
        interrupt_controller=SimpleNamespace(
            request_interrupt=MagicMock(
                return_value=SimpleNamespace(
                    status="interrupted",
                    session_key="qq:1",
                    message="已中断",
                )
            )
        ),
    )
    adapter_mod = sys.modules["ncatbot.core.adapter.adapter"]
    adapter_mod.websockets.connect("ws://example.invalid", open_timeout=1)
    assert adapter_mod._captured_connect_calls[-1]["open_timeout"] == 1
    assert sys.modules["ncatbot.utils"].ncatbot_config.root == ""
    assert channel._bot is None
    assert channel._is_allowed("1") is True
    assert channel._is_allowed("2") is False
    from infra.channels.qq_channel.compat import (
        download_to_temp,
        extract_cq_images,
        is_local,
        local_to_base64,
    )

    assert extract_cq_images("hello [CQ:image,url=http://x/a.jpg]") == (
        "hello",
        ["http://x/a.jpg"],
    )

    scheduled = []
    real_create_task = asyncio.create_task

    def _run_coroutine_threadsafe(coro, loop):
        scheduled.append(real_create_task(coro))
        return SimpleNamespace(result=lambda timeout=None: True)

    monkeypatch.setattr(
        lifecycle.asyncio,
        "run_coroutine_threadsafe",
        _run_coroutine_threadsafe,
    )
    await channel.start()
    assert bus.outbound[0][0] == "qq"
    adapter_mod.websockets.connect("ws://example.invalid", open_timeout=1)
    assert adapter_mod._captured_connect_calls[-1]["open_timeout"] == 7.5
    assert sys.modules["ncatbot.utils"].ncatbot_config.root == "1"
    assert sys.modules["ncatbot.utils"].ncatbot_config.plugin.plugins_dir == str(
        ncatbot_dir / "plugins"
    )
    channel._channel_hub._conversation.ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="qq:gqq:100",
            role_id="mira",
            channel="qq",
            chat_id="gqq:100",
        )
    )

    async def _drain(coro):
        return await coro

    channel._run_on_bot_loop = AsyncMock(side_effect=_drain)

    await channel._bot.startup_handler(SimpleNamespace())
    await channel._bot.private_handler(
        SimpleNamespace(user_id="1", raw_message="hi [CQ:image,url=http://x/a.jpg]")
    )
    await channel._bot.group_handler(
        SimpleNamespace(group_id="100", user_id="1", raw_message="hello")
    )
    await channel._bot.private_handler(
        SimpleNamespace(user_id="1", raw_message="/stop")
    )
    await channel._bot.group_handler(
        SimpleNamespace(group_id="100", user_id="1", raw_message="/stop")
    )
    if scheduled:
        await asyncio.gather(*scheduled)
    assert len(bus.inbound) == 2
    assert bus.inbound[0].metadata["chat_type"] == "private"
    assert bus.inbound[1].metadata["chat_type"] == "group"
    assert bus.inbound[0].session_key == "role:mira"
    assert bus.inbound[0].metadata["role_id"] == "mira"
    assert bus.inbound[0].metadata["thread_id"] == "thread:mira:qq:1"
    assert bus.inbound[1].session_key == "role:mira"
    assert bus.inbound[1].metadata["thread_id"] == "thread:mira:qq:gqq:100"
    assert channel._interrupt_controller.request_interrupt.call_count == 2
    assert [
        call.kwargs["session_key"]
        for call in channel._interrupt_controller.request_interrupt.call_args_list
    ] == ["role:mira", "role:mira"]

    channel._run_on_bot_loop = AsyncMock(side_effect=_drain)
    sample = tmp_path / "image.bin"
    sample.write_bytes(b"abc")
    await channel.send("1", "pong")
    await channel.send("gqq:100", "group pong")
    await channel.send_file("1", str(sample), name="x.bin")
    await channel.send_image("1", str(sample))
    await channel._on_response(
        OutboundMessage(
            channel="qq",
            chat_id="gqq:100",
            content="reply",
            metadata={
                "session_key_override": "role:mira",
                "role_id": "mira",
                "thread_id": "thread:mira:qq:gqq:100",
            },
            committed_message_id="role:mira:0",
        )
    )
    assert channel._api.calls
    assert is_local(str(sample)) is True
    assert is_local("https://example.com/x.jpg") is False
    assert local_to_base64(str(sample)).startswith("base64://")

    test_attachments = AttachmentStore(tmp_path / "uploads")
    paths = await download_to_temp(
        ["http://x/a.png", "http://x/b.png"],
        requester,
        test_attachments,
    )
    assert len(paths) == 1

    channel._bot_loop = None
    pending = asyncio.sleep(0)
    with pytest.raises(RuntimeError):
        await mod.QQChannel._run_on_bot_loop(channel, pending)
    pending.close()
    await channel.stop()
    assert bus.outbound == []
    assert {
        "session_key": "role:mira",
        "message_id": "role:mira:0",
        "thread_id": "thread:mira:qq:gqq:100",
        "delivery_status": "sent",
        "external_message_id": "",
    } in session_manager.delivery_updates


def test_napcat_qq_declares_no_stream_or_prompt_hooks(monkeypatch, tmp_path):
    mod = _import_qq_channel(monkeypatch)
    channel = mod.QQChannel(
        "42", _Bus(), _SessionManager(tmp_path), http_requester=SimpleNamespace()
    )
    directory = ChannelDirectory()
    directory.bind({"qq": channel}.get)

    assert not directory.supports_stream_events("qq", "123")
    assert directory.system_prompt_hint("qq", "123") == ""
    assert directory.default_chat_type("qq") == "unknown"


@pytest.mark.asyncio
async def test_qq_channel_buffers_received_input_during_pause(monkeypatch, tmp_path):
    mod = _import_qq_channel(monkeypatch)
    bus = _Bus()
    sessions = _SessionManager(tmp_path)
    channel = mod.QQChannel("42", bus, sessions, http_requester=SimpleNamespace())
    channel._channel_hub = None
    channel.pause_intake()
    message = InboundMessage(
        channel="qq", sender="1", chat_id="1", content="during save"
    )
    await channel._publish_inbound(message)
    assert bus.inbound == []
    channel.resume_intake()
    await channel._intake.drain()
    assert bus.inbound == [message]
    await channel._intake.close()


@pytest.mark.asyncio
async def test_qq_channel_notifies_pending_input_before_disconnect(
    monkeypatch, tmp_path
):
    mod = _import_qq_channel(monkeypatch)
    send = AsyncMock()
    monkeypatch.setattr(mod.QQChannel, "send", send)
    bus = _Bus()
    sessions = _SessionManager(tmp_path)
    channel = mod.QQChannel("42", bus, sessions, http_requester=SimpleNamespace())
    channel._channel_hub = None
    channel.pause_intake()
    await channel._publish_inbound(
        InboundMessage(channel="qq", sender="1", chat_id="1", content="pending")
    )
    await channel.stop()
    assert bus.inbound == []
    send.assert_awaited_once()
    assert "重新发送" in send.await_args.args[1]


@pytest.mark.asyncio
async def test_qq_private_trace_sends_forward_then_final_and_clears_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    mod = _import_qq_channel(monkeypatch)
    bus = _Bus()
    session_manager = _SessionManager()
    event_bus = EventBus()
    channel = mod.QQChannel(
        "42",
        bus,
        session_manager,
        allow_from=["1"],
        event_bus=event_bus,
        http_requester=SimpleNamespace(get=AsyncMock()),
    )
    await channel.start()

    calls: list[tuple[str, object, object]] = []

    async def _drain(coro):
        return await coro

    async def _fake_send_private_forward_msg(user_id, **payload):
        calls.append(("forward", user_id, payload))

    async def _fake_send_private_text(user_id, content):
        calls.append(("text", user_id, content))

    async def _fake_get_login_info():
        return SimpleNamespace(user_id="42", nickname="Bot")

    channel._run_on_bot_loop = AsyncMock(side_effect=_drain)
    channel._api.send_private_forward_msg = _fake_send_private_forward_msg
    channel._api.send_private_text = _fake_send_private_text
    channel._api.get_login_info = _fake_get_login_info
    channel._workspace = tmp_path
    (tmp_path / "memory").mkdir(parents=True, exist_ok=True)
    (tmp_path / "memory" / "SELF.md").write_text(
        "# Steria 的自我认知\n- 我是 Steria，负责陪伴和协作。\n",
        encoding="utf-8",
    )

    await event_bus.observe(
        TurnStarted(
            session_key="qq:1",
            channel="qq",
            chat_id="1",
            content="帮我看看最近的提交",
            timestamp=__import__("datetime").datetime.now(),
        )
    )
    await event_bus.observe(
        ToolCallStarted(
            session_key="qq:1",
            channel="qq",
            chat_id="1",
            iteration=1,
            call_id="call-1",
            tool_name="fetch_messages",
            arguments={"description": "查最近消息", "query": "最近提交"},
        )
    )
    await event_bus.observe(
        ToolCallCompleted(
            session_key="qq:1",
            channel="qq",
            chat_id="1",
            iteration=1,
            call_id="call-1",
            tool_name="fetch_messages",
            arguments={"description": "查最近消息", "query": "最近提交"},
            final_arguments={"description": "查最近消息", "query": "最近提交"},
            status="ok",
            result_preview='{"count": 21, "matched_count": 1}',
        )
    )

    await channel._on_response(
        OutboundMessage(
            channel="qq",
            chat_id="1",
            content="我看到了，最近主要是 QQ tracing 的改动。",
            thinking="先确认这轮是否有工具调用，再组织结论。",
        )
    )

    assert [item[0] for item in calls] == ["forward", "text"]
    forward_payload = cast(dict[str, Any], calls[0][2])
    assert forward_payload["news"] == [
        {"text": "Steria：【模型思路】"},
        {"text": "Steria：【工具链】"},
    ]
    assert "fetch_messages" in str(forward_payload)
    assert "命中 1 条，返回上下文 21 条" in str(forward_payload)
    assert calls[1] == ("text", 1, "我看到了，最近主要是 QQ tracing 的改动。")
    assert "qq:1" not in channel._trace_states


@pytest.mark.asyncio
async def test_qq_private_trace_skips_empty_trace(monkeypatch: pytest.MonkeyPatch):
    mod = _import_qq_channel(monkeypatch)
    bus = _Bus()
    session_manager = _SessionManager()
    event_bus = EventBus()
    channel = mod.QQChannel(
        "42",
        bus,
        session_manager,
        allow_from=["1"],
        event_bus=event_bus,
        http_requester=SimpleNamespace(get=AsyncMock()),
    )
    await channel.start()

    calls: list[tuple[str, object, object]] = []

    async def _drain(coro):
        return await coro

    async def _fake_send_private_forward_msg(user_id, **payload):
        calls.append(("forward", user_id, payload))

    async def _fake_send_private_text(user_id, content):
        calls.append(("text", user_id, content))

    async def _fake_get_login_info():
        return SimpleNamespace(user_id="42", nickname="Bot")

    channel._run_on_bot_loop = AsyncMock(side_effect=_drain)
    channel._api.send_private_forward_msg = _fake_send_private_forward_msg
    channel._api.send_private_text = _fake_send_private_text
    channel._api.get_login_info = _fake_get_login_info

    await event_bus.observe(
        TurnStarted(
            session_key="qq:1",
            channel="qq",
            chat_id="1",
            content="好",
            timestamp=__import__("datetime").datetime.now(),
        )
    )

    await channel._on_response(
        OutboundMessage(
            channel="qq",
            chat_id="1",
            content="嗯，收到。",
            thinking=None,
        )
    )

    assert [item[0] for item in calls] == ["text"]
    assert calls[0] == ("text", 1, "嗯，收到。")


@pytest.mark.asyncio
async def test_qq_channel_records_failed_delivery_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    mod = _import_qq_channel(monkeypatch)
    bus = _Bus()
    session_manager = _SessionManager(tmp_path)
    channel = mod.QQChannel(
        "42",
        bus,
        session_manager,
        allow_from=["1"],
        event_bus=EventBus(),
        http_requester=SimpleNamespace(get=AsyncMock()),
    )
    await channel.start()
    channel._channel_hub._conversation.ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="qq:1",
            role_id="mira",
            channel="qq",
            chat_id="1",
        )
    )

    async def _drain(coro):
        return await coro

    async def _boom(*args, **kwargs):
        raise RuntimeError("send failed")

    channel._run_on_bot_loop = AsyncMock(side_effect=_drain)
    channel._api.send_private_text = _boom

    with pytest.raises(RuntimeError, match="send failed"):
        await channel._on_response(
            OutboundMessage(
                channel="qq",
                chat_id="1",
                content="reply",
                metadata={
                    "session_key_override": "role:mira",
                    "role_id": "mira",
                    "thread_id": "thread:mira:qq:1",
                },
                committed_message_id="role:mira:0",
            )
        )

    assert session_manager.delivery_updates[-1] == {
        "session_key": "role:mira",
        "message_id": "role:mira:0",
        "thread_id": "thread:mira:qq:1",
        "delivery_status": "failed",
        "external_message_id": "",
    }
    await channel.stop()
