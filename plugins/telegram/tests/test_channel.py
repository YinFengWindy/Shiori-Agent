"""TelegramChannel 行为测试：迁入插件前的内置渠道测试原样搬来（#363 T4）。"""

from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from bus.event_bus import EventBus
from bus.events import InboundMessage, OutboundMessage
from bus.events_lifecycle import (
    StreamDeltaReady,
    ToolCallCompleted,
    ToolCallStarted,
)
from core.common.channel_directory import ChannelDirectory
from core.roles import RoleStore
from conversation.service import LegacySessionDescriptor
from infra.channels.contract import ChannelContext

_CHANNEL_PACKAGE = "plugins.telegram.backend.channel"
_CHANNEL_DIR = Path(__file__).resolve().parents[1] / "backend" / "channel"


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


def _import_telegram_channel(monkeypatch: pytest.MonkeyPatch):
    telegram = types.ModuleType("telegram")
    telegram_constants = types.ModuleType("telegram.constants")
    telegram_error = types.ModuleType("telegram.error")
    telegram_ext = types.ModuleType("telegram.ext")

    class Update:
        ALL_TYPES = ["message"]

    class Bot:
        async def edit_message_text(self, *args, **kwargs):
            return True

    class BotCommand:
        def __init__(self, command, description):
            self.command = command
            self.description = description

    class MessageEntity:
        def __init__(self, *, type, offset, length):
            self.type = type
            self.offset = offset
            self.length = length

    class TelegramError(Exception):
        pass

    class Conflict(TelegramError):
        pass

    class InvalidToken(TelegramError):
        pass

    class BadRequest(TelegramError):
        pass

    class RetryAfter(TelegramError):
        def __init__(self, retry_after=1.0):
            super().__init__(retry_after)
            self.retry_after = retry_after

    class NetworkError(TelegramError):
        pass

    class TimedOut(TelegramError):
        pass

    class _Filter:
        def __and__(self, other):
            return self

        def __invert__(self):
            return self

    class _Document:
        ALL = _Filter()

    class MessageHandler:
        def __init__(self, flt, callback):
            self.filter = flt
            self.callback = callback

    class CommandHandler:
        def __init__(self, command, callback):
            self.command = command
            self.callback = callback

    class _Updater:
        def __init__(self):
            self.running = False
            self.error_callback = None

        async def start_polling(self, **kwargs):
            self.running = True
            self.error_callback = kwargs.get("error_callback")

        async def stop(self):
            self.running = False

    class _Builder:
        def __init__(self):
            self._token = None

        def token(self, token):
            self._token = token
            return self

        def build(self):
            return _Application(self._token)

    class _Application:
        def __init__(self, token):
            self.token = token
            self.running = False
            self.bot = SimpleNamespace(
                send_message=AsyncMock(return_value=SimpleNamespace(message_id=99)),
                edit_message_text=AsyncMock(),
                send_document=AsyncMock(),
                send_photo=AsyncMock(),
                send_chat_action=AsyncMock(),
                delete_message=AsyncMock(),
                get_file=AsyncMock(),
                set_my_commands=AsyncMock(),
            )
            self.updater = _Updater()
            self.handlers = []

        @classmethod
        def builder(cls):
            return _Builder()

        async def initialize(self):
            return None

        async def start(self):
            self.running = True

        async def stop(self):
            self.running = False

        async def shutdown(self):
            return None

        def add_handler(self, handler):
            self.handlers.append(handler)

    telegram.Bot = Bot
    telegram.BotCommand = BotCommand
    telegram.MessageEntity = MessageEntity
    telegram.Update = Update
    telegram_constants.ChatAction = SimpleNamespace(TYPING="typing")
    telegram_error.Conflict = Conflict
    telegram_error.InvalidToken = InvalidToken
    telegram_error.BadRequest = BadRequest
    telegram_error.NetworkError = NetworkError
    telegram_error.RetryAfter = RetryAfter
    telegram_error.TelegramError = TelegramError
    telegram_error.TimedOut = TimedOut
    telegram_ext.Application = _Application
    telegram_ext.ContextTypes = SimpleNamespace(DEFAULT_TYPE=object)
    telegram_ext.CommandHandler = CommandHandler
    telegram_ext.MessageHandler = MessageHandler
    telegram_ext.filters = SimpleNamespace(
        TEXT=_Filter(),
        COMMAND=_Filter(),
        PHOTO=_Filter(),
        Document=_Document(),
    )
    monkeypatch.setitem(sys.modules, "telegram", telegram)
    monkeypatch.setitem(sys.modules, "telegram.constants", telegram_constants)
    monkeypatch.setitem(sys.modules, "telegram.error", telegram_error)
    monkeypatch.setitem(sys.modules, "telegram.ext", telegram_ext)
    # 渠道包绑定的是上面的假 telegram 模块；测试结束后恢复原有模块，避免污染
    # 其他用真实 python-telegram-bot 导入本包的测试。
    names = [_CHANNEL_PACKAGE] + [
        f"{_CHANNEL_PACKAGE}.{path.stem}"
        for path in _CHANNEL_DIR.glob("*.py")
        if path.stem != "__init__"
    ]
    for name in names:
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
        del sys.modules[name]
    return importlib.import_module(_CHANNEL_PACKAGE)


@pytest.mark.asyncio
async def test_telegram_channel_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    mod = _import_telegram_channel(monkeypatch)
    bus = _Bus()
    event_bus = EventBus()
    session_manager = _SessionManager(tmp_path)
    role_store = RoleStore(tmp_path)
    role_store.create_role(
        role_id="mira",
        name="Mira",
        description="bound telegram role",
        system_prompt="you are mira",
    )
    role_store.update_role(
        "mira",
        channel_bindings=[
            {
                "channel": "telegram",
                "chat_id": "123",
                "chat_type": "private",
            }
        ],
    )
    interrupt_controller = MagicMock()
    interrupt_controller.request_interrupt.return_value = SimpleNamespace(
        status="interrupted",
        session_key="telegram:123",
        message="已中断",
    )
    channel = mod.TelegramChannel(
        "token",
        bus,
        session_manager,
        bot_commands=[
            ("memorystatus", "查看记忆整理状态"),
            ("kvcache", "查看 KVCache 状态"),
        ],
        event_bus=event_bus,
        interrupt_controller=interrupt_controller,
    )
    channel._telegram_outbound_limiter = mod.TelegramOutboundLimiter(
        send_interval_s=0.0,
        edit_interval_s=0.0,
        typing_interval_s=0.0,
        global_interval_s=0.0,
        retry_padding_s=0.0,
    )
    channel._live_edit_queue = mod.TelegramLiveEditQueue(
        min_interval_s=0.0,
        limiter=channel._telegram_outbound_limiter,
    )
    monkeypatch.setattr(mod, "send_markdown", AsyncMock())
    monkeypatch.setattr(mod, "send_stream_markdown", AsyncMock())
    monkeypatch.setattr(mod, "send_thinking_block", AsyncMock())
    await channel.start()
    hub = channel._channel_hub
    assert hub is not None
    channel._channel_hub = None
    assert len(channel._app.handlers) == 6
    assert [
        cmd.command for cmd in channel._app.bot.set_my_commands.await_args.args[0]
    ] == [
        "memorystatus",
        "kvcache",
        "stop",
        "chatid",
    ]
    assert bus.outbound[0][0] == "telegram"

    class _File:
        def __init__(self, suffix):
            self.suffix = suffix

        async def download_to_drive(self, path):
            Path(path).write_text("x", encoding="utf-8")

    channel._app.bot.get_file = AsyncMock(
        side_effect=[
            _File(".jpg"),
            _File(".txt"),
            _File(".jpg"),
            _File(".txt"),
            _File(".md"),
        ]
    )
    context = SimpleNamespace(bot=channel._app.bot)
    reply_photo = [SimpleNamespace(file_id="p1")]
    reply_doc = SimpleNamespace(file_id="d1", file_name="note.txt")
    reply_user = SimpleNamespace(id=2, username="other")
    reply_msg = SimpleNamespace(
        text="原消息",
        caption="",
        photo=reply_photo,
        document=reply_doc,
        from_user=reply_user,
        message_id=9,
    )
    update = SimpleNamespace(
        effective_message=SimpleNamespace(
            text="你好",
            message_id=1,
            reply_to_message=reply_msg,
            photo=None,
            document=None,
        ),
        effective_chat=SimpleNamespace(id=123),
        effective_user=SimpleNamespace(id=1, username="Alice"),
    )
    await channel._on_message(update, context)
    assert len(bus.inbound) == 1
    assert bus.inbound[0].metadata["reply_to_sender"] == "@other"
    assert len(bus.inbound[0].media) == 2

    stop_update = SimpleNamespace(
        effective_message=SimpleNamespace(text="/stop", message_id=99),
        effective_chat=SimpleNamespace(id=123),
        effective_user=SimpleNamespace(id=1, username="Alice"),
    )
    await channel._on_stop_command(stop_update, context)
    interrupt_controller.request_interrupt.assert_called_once_with(
        session_key="telegram:123",
        sender="1",
        command="/stop",
    )
    assert len(bus.inbound) == 1

    status_update = SimpleNamespace(
        effective_message=SimpleNamespace(text="/memorystatus", message_id=100),
        effective_chat=SimpleNamespace(id=123),
        effective_user=SimpleNamespace(id=1, username="Alice"),
    )
    await channel._on_command(status_update, context)
    assert len(bus.inbound) == 2
    assert bus.inbound[1].content == "/memorystatus"
    assert bus.inbound[1].metadata["username"] == "Alice"

    kvcache_update = SimpleNamespace(
        effective_message=SimpleNamespace(text="/kvcache 5", message_id=101),
        effective_chat=SimpleNamespace(id=123),
        effective_user=SimpleNamespace(id=1, username="Alice"),
    )
    await channel._on_command(kvcache_update, context)
    assert len(bus.inbound) == 3
    assert bus.inbound[2].content == "/kvcache 5"
    assert bus.inbound[2].metadata["username"] == "Alice"

    photo_update = SimpleNamespace(
        effective_message=SimpleNamespace(
            photo=[SimpleNamespace(file_id="main"), SimpleNamespace(file_id="main2")],
            message_id=2,
            caption="图说",
            reply_to_message=SimpleNamespace(
                photo=[SimpleNamespace(file_id="rp")],
                text="",
                caption="",
                from_user=reply_user,
                message_id=10,
            ),
        ),
        effective_chat=SimpleNamespace(id=123),
        effective_user=SimpleNamespace(id=1, username="Alice"),
    )
    await channel._on_photo(photo_update, context)

    doc_update = SimpleNamespace(
        effective_message=SimpleNamespace(
            document=SimpleNamespace(
                file_id="doc1", file_name="a.md", mime_type="text/plain"
            ),
            message_id=3,
            caption="",
            reply_to_message=None,
        ),
        effective_chat=SimpleNamespace(id=123),
        effective_user=SimpleNamespace(id=1, username="Alice"),
    )
    await channel._on_document(doc_update, context)
    assert len(bus.inbound) == 5
    assert bus.inbound[-1].metadata["document_filename"] == "a.md"

    assert channel._resolve_chat_id("123") == "123"
    channel.user_map["alice"] = "456"
    assert channel._resolve_chat_id("@Alice") == "456"
    with pytest.raises(ValueError):
        channel._resolve_chat_id("@missing")

    hub._conversation.ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="telegram:123",
            role_id="mira",
            channel="telegram",
            chat_id="123",
        )
    )
    channel._channel_hub = hub
    await channel.send("123", "hi")
    await channel.send_stream("123", "stream hi")
    sample = tmp_path / "doc.txt"
    sample.write_text("x", encoding="utf-8")
    # Push senders hand back the id of the message Telegram created.
    channel._app.bot.send_document.return_value = SimpleNamespace(message_id=8)
    channel._app.bot.send_photo.return_value = SimpleNamespace(message_id=7)
    assert (
        await channel.send_file("123", str(sample), name="doc.txt", caption="cap")
        == "8"
    )
    assert await channel.send_image("123", "https://example.com/img.jpg") == "7"
    await channel.send_image("123", str(sample))
    await channel._on_response(
        OutboundMessage(
            channel="telegram",
            chat_id="123",
            content="pong",
            metadata={
                "session_key_override": "role:mira",
                "role_id": "mira",
                "thread_id": "thread:mira:telegram:123",
            },
        )
    )
    assert mod.send_markdown.await_count == 3
    assert mod.send_stream_markdown.await_count == 1
    sender = channel.create_stream_sender("123")
    assert sender is not None
    await sender({"thinking_delta": "先想一点"})
    await sender("流式片段")
    await sender(
        "继续补充一大段内容继续补充一大段内容继续补充一大段内容继续补充一大段内容"
    )
    assert channel._app.bot.send_message.await_count >= 1
    before_send = channel._app.bot.send_message.await_count
    before_edit = channel._app.bot.edit_message_text.await_count
    live = mod.TelegramLiveTextMessage(
        channel._app.bot,
        mod.TelegramLiveEditQueue(min_interval_s=0.0),
        123,
    )
    await asyncio.gather(
        live.update("工具调用\na"),
        live.update("工具调用\nb"),
        live.update("工具调用\nc"),
    )
    assert channel._app.bot.send_message.await_count == before_send + 1
    assert channel._app.bot.edit_message_text.await_count >= before_edit + 1
    await event_bus.observe(
        StreamDeltaReady(
            session_key="telegram:456",
            channel="telegram",
            chat_id="456",
            content_delta="事件片段",
        )
    )
    assert channel._active_streams.get("456") is None
    await asyncio.sleep(0)
    assert channel._live_messages.get("telegram:456") is not None
    channel._thinking_live_next_at["telegram:456"] = 0.0
    await event_bus.observe(
        StreamDeltaReady(
            session_key="telegram:456",
            channel="telegram",
            chat_id="456",
            thinking_delta="事件思考",
        )
    )
    await asyncio.sleep(0)
    live_texts = [
        call.kwargs.get("text", "")
        for call in (
            channel._app.bot.send_message.await_args_list
            + channel._app.bot.edit_message_text.await_args_list
        )
    ]
    assert any(
        "临时回复" in text
        and "事件片段" in text
        and "思考过程" in text
        and "事件思考" in text
        for text in live_texts
    )
    assert any(
        text.find("思考过程") < text.find("临时回复")
        for text in live_texts
        if "思考过程" in text and "临时回复" in text
    )
    before_threshold_edit = channel._app.bot.edit_message_text.await_count
    await event_bus.observe(
        StreamDeltaReady(
            session_key="telegram:456",
            channel="telegram",
            chat_id="456",
            thinking_delta="继续分析" * 60,
        )
    )
    await asyncio.sleep(0)
    assert channel._app.bot.edit_message_text.await_count > before_threshold_edit
    await event_bus.observe(
        ToolCallStarted(
            session_key="telegram:456",
            channel="telegram",
            chat_id="456",
            iteration=1,
            call_id="call-1",
            tool_name="shell",
            arguments={"cmd": "df -h", "description": "查看磁盘空间"},
        )
    )
    await event_bus.observe(
        ToolCallCompleted(
            session_key="telegram:456",
            channel="telegram",
            chat_id="456",
            iteration=1,
            call_id="call-1",
            tool_name="shell",
            arguments={"cmd": "df -h", "description": "查看磁盘空间"},
            final_arguments={"cmd": "df -h", "description": "查看磁盘空间"},
            status="ok",
            result_preview="exit=0",
        )
    )
    await asyncio.sleep(0)
    if channel._live_tasks:
        await asyncio.gather(*list(channel._live_tasks))
    assert channel._live_messages.get("telegram:456") is not None
    assert any(
        "工具调用" in call.kwargs.get("text", "")
        for call in channel._app.bot.send_message.await_args_list
    )
    tool_texts = [
        call.kwargs.get("text", "")
        for call in (
            channel._app.bot.send_message.await_args_list
            + channel._app.bot.edit_message_text.await_args_list
        )
        if "工具调用" in call.kwargs.get("text", "")
    ]
    assert any(
        "shell: 查看磁盘空间" in text and "df -h" in text and "✅" in text
        for text in tool_texts
    )
    assert all("exit=0" not in text for text in tool_texts)
    long_text, long_html = mod._format_turn_live(
        [
            mod._ToolLiveLine(
                call_id="long",
                tool_name="shell",
                intent="查看长输出",
                target="工具开头" + "x" * 1300 + "工具结尾",
                status="done",
            )
        ],
        "回复开头" + "y" * 1300 + "回复结尾",
        "思考开头" + "z" * 1600 + "思考结尾",
    )
    assert "思考结尾" in long_text and "思考开头" not in long_text
    assert "工具结尾" in long_text and "工具开头" not in long_text
    assert "回复结尾" in long_text and "回复开头" not in long_text
    assert "<blockquote>" in long_html and "<pre>" in long_html
    channel.user_map["group"] = "-1001"
    assert channel.create_stream_sender("@group") is None
    await channel._on_response(
        OutboundMessage(
            channel="telegram",
            chat_id="123",
            content="final",
            metadata={
                "streamed_reply": True,
                "role_id": "mira",
                "session_key_override": "role:mira",
                "thread_id": "thread:mira:telegram:123",
            },
        )
    )
    assert channel._app.bot.edit_message_text.await_count >= 1
    assert mod.send_markdown.await_count == 3
    assert mod.send_stream_markdown.await_count == 1
    mod.send_thinking_block.reset_mock()
    before_final_markdown = mod.send_markdown.await_count
    before_delete = channel._app.bot.delete_message.await_count
    await channel._on_response(
        OutboundMessage(
            channel="telegram",
            chat_id="456",
            content="事件最终回复",
            thinking="继续分析",
        )
    )
    assert channel._app.bot.delete_message.await_count == before_delete + 1
    mod.send_thinking_block.assert_awaited_once()
    assert mod.send_markdown.await_count == before_final_markdown + 2
    snapshot_text = mod.send_markdown.await_args_list[-2].args[2]
    assert "工具调用" in snapshot_text
    assert "事件思考继续分析" not in snapshot_text
    assert "临时回复" not in snapshot_text
    assert snapshot_text.startswith("```")

    mod.send_thinking_block.reset_mock()
    sender = channel.create_stream_sender("123")
    assert sender is not None
    await sender({"thinking_delta": "分析中"})
    await channel._on_response(
        OutboundMessage(
            channel="telegram",
            chat_id="123",
            content="final",
            thinking="分析中",
            metadata={
                "streamed_reply": True,
                "role_id": "mira",
                "session_key_override": "role:mira",
                "thread_id": "thread:mira:telegram:123",
            },
            committed_message_id="role:mira:0",
        )
    )
    mod.send_thinking_block.assert_awaited_once()
    last_edit = channel._app.bot.edit_message_text.await_args_list[-1].kwargs["text"]
    assert last_edit == "final"

    channel._app.bot.send_chat_action = AsyncMock(
        side_effect=[mod.TimedOut("x"), mod.NetworkError("x"), None]
    )
    monkeypatch.setattr(mod.asyncio, "sleep", AsyncMock(return_value=None))
    await channel._safe_send_typing(context, 123)
    channel._app.bot.send_chat_action = AsyncMock(side_effect=RuntimeError("boom"))
    await channel._safe_send_typing(context, 123)

    created = []
    real_create_task = asyncio.create_task

    def _capture_task(coro):
        task = real_create_task(coro)
        created.append(task)
        return task

    monkeypatch.setattr(mod.asyncio, "create_task", _capture_task)
    channel._on_polling_error(mod.Conflict("conflict"))
    if created:
        await asyncio.gather(*created)
    channel._on_polling_error(mod.TelegramError("warn"))
    await channel.stop()
    assert bus.outbound == []
    assert event_bus._handlers == {}
    await channel.start()
    assert len(bus.outbound) == 1
    assert all(len(handlers) == 1 for handlers in event_bus._handlers.values())
    await channel.stop()
    assert bus.outbound == []
    assert {
        "session_key": "role:mira",
        "message_id": "role:mira:0",
        "thread_id": "thread:mira:telegram:123",
        "delivery_status": "sent",
        "external_message_id": "99",
    } in session_manager.delivery_updates

    merged, meta = mod._build_inbound_text_with_reply("hi", None)
    assert (merged, meta) == ("hi", {})
    merged, meta = mod._build_inbound_text_with_reply(
        "hi",
        SimpleNamespace(text="", caption="", photo=[1], from_user=None, message_id=11),
    )
    assert "[图片]" in merged


def test_telegram_hooks_keep_private_streaming_and_rendering_rules(
    monkeypatch, tmp_path
):
    mod = _import_telegram_channel(monkeypatch)
    channel = mod.TelegramChannel("token", _Bus(), _SessionManager(tmp_path))
    directory = ChannelDirectory()
    directory.bind({"telegram": channel}.get)

    assert directory.supports_stream_events("telegram", "123")
    assert not directory.supports_stream_events("telegram", "-1001")
    assert not directory.supports_stream_events("telegram", "@alice")
    assert directory.default_chat_type("telegram") == "private"
    hint = directory.system_prompt_hint("telegram", "123")
    assert hint.startswith("## Telegram 渲染限制（硬性规则）\n")
    assert "都不得输出 Markdown 表格（`| ... |` 语法）" in hint
    assert hint.endswith("• 功耗：350W+")


@pytest.mark.asyncio
async def test_telegram_channel_buffers_received_input_during_pause(
    monkeypatch, tmp_path
):
    mod = _import_telegram_channel(monkeypatch)
    bus = _Bus()
    channel = mod.TelegramChannel("token", bus, _SessionManager(tmp_path))
    channel._channel_hub = None
    channel.pause_intake()
    message = InboundMessage(
        channel="telegram", sender="1", chat_id="1", content="during save"
    )
    await channel._publish_inbound(message)
    assert bus.inbound == []
    channel.resume_intake()
    await channel._intake.drain()
    assert bus.inbound == [message]
    await channel._intake.close()


@pytest.mark.asyncio
async def test_telegram_channel_notifies_pending_input_before_disconnect(
    monkeypatch, tmp_path
):
    mod = _import_telegram_channel(monkeypatch)
    send = AsyncMock()
    monkeypatch.setattr(mod.TelegramChannel, "send", send)
    bus = _Bus()
    channel = mod.TelegramChannel("token", bus, _SessionManager(tmp_path))
    channel._channel_hub = None
    channel.pause_intake()
    await channel._publish_inbound(
        InboundMessage(channel="telegram", sender="1", chat_id="1", content="pending")
    )
    await channel.stop()
    assert bus.inbound == []
    send.assert_awaited_once()
    assert "重新发送" in send.await_args.args[1]


@pytest.mark.asyncio
async def test_telegram_channel_rejects_legacy_binding_without_account(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    mod = _import_telegram_channel(monkeypatch)
    bus = _Bus()
    session_manager = _SessionManager(tmp_path)
    role_store = RoleStore(tmp_path)
    role_store.create_role(
        role_id="mira",
        name="Mira",
        description="bound telegram role",
        system_prompt="you are mira",
    )
    role_store.update_role(
        "mira",
        channel_bindings=[
            {
                "channel": "telegram",
                "chat_id": "123",
                "chat_type": "private",
            }
        ],
    )

    interrupt_controller = MagicMock()
    event_bus = EventBus()
    channel = mod.TelegramChannel(
        token="token",
        bus=bus,
        session_manager=session_manager,
        event_bus=event_bus,
        interrupt_controller=interrupt_controller,
    )
    monkeypatch.setattr(mod, "send_markdown", AsyncMock())
    monkeypatch.setattr(mod, "send_stream_markdown", AsyncMock())
    monkeypatch.setattr(mod, "send_thinking_block", AsyncMock())
    await channel.start()
    context = SimpleNamespace(bot=channel._app.bot)
    update = SimpleNamespace(
        effective_message=SimpleNamespace(
            text="你好",
            message_id=1,
            reply_to_message=None,
            photo=None,
            document=None,
        ),
        effective_chat=SimpleNamespace(id=123),
        effective_user=SimpleNamespace(id=1, username="Alice"),
    )

    await channel._on_message(update, context)

    assert bus.inbound == []
    await channel.stop()


@pytest.mark.asyncio
async def test_telegram_group_rejects_legacy_binding_without_account(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    mod = _import_telegram_channel(monkeypatch)
    bus = _Bus()
    role_store = RoleStore(tmp_path)
    role_store.create_role(role_id="mira", name="Mira", system_prompt="you are mira")
    role_store.update_role(
        "mira",
        channel_bindings=[
            {
                "channel": "telegram",
                "chat_id": "-100",
                "chat_type": "group",
                "blocked_senders": ["Troll"],
            }
        ],
    )
    interrupt_controller = MagicMock()
    channel = mod.TelegramChannel(
        token="token",
        bus=bus,
        session_manager=_SessionManager(tmp_path),
        event_bus=EventBus(),
        interrupt_controller=interrupt_controller,
    )
    monkeypatch.setattr(mod, "send_markdown", AsyncMock())
    await channel.start()
    context = SimpleNamespace(bot=channel._app.bot)

    def _update(user_id: int, username: str, text: str, message_id: int):
        return SimpleNamespace(
            effective_message=SimpleNamespace(
                text=text,
                message_id=message_id,
                reply_to_message=None,
                photo=None,
                document=None,
            ),
            effective_chat=SimpleNamespace(id=-100, type="group"),
            effective_user=SimpleNamespace(id=user_id, username=username),
        )

    # The blacklist entry names a username; it matches case-insensitively.
    await channel._on_message(_update(5, "troll", "hi", 1), context)
    await channel._on_stop_command(_update(5, "troll", "/stop", 2), context)
    await channel._on_message(_update(6, "friend", "hello", 3), context)

    assert bus.inbound == []
    interrupt_controller.request_interrupt.assert_not_called()
    await channel.stop()


@pytest.mark.asyncio
async def test_telegram_rejected_sender_triggers_no_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    mod = _import_telegram_channel(monkeypatch)
    bus = _Bus()
    role_store = RoleStore(tmp_path)
    role_store.create_role(role_id="mira", name="Mira", system_prompt="you are mira")
    role_store.update_role(
        "mira",
        channel_bindings=[
            {
                "channel": "telegram",
                "chat_id": "-100",
                "chat_type": "group",
                "blocked_senders": ["@troll"],
            }
        ],
    )
    channel = mod.TelegramChannel(
        token="token",
        bus=bus,
        session_manager=_SessionManager(tmp_path),
        event_bus=EventBus(),
    )
    await channel.start()
    typing = AsyncMock()
    remember = AsyncMock()
    get_file = AsyncMock()
    monkeypatch.setattr(channel, "_safe_send_typing", typing)
    monkeypatch.setattr(channel, "_remember_username", remember)
    channel._app.bot.get_file = get_file
    context = SimpleNamespace(bot=channel._app.bot)
    reply = SimpleNamespace(
        text="",
        caption="",
        photo=[SimpleNamespace(file_id="rp")],
        document=SimpleNamespace(file_id="rd", file_name="r.txt"),
        from_user=SimpleNamespace(id=2, username="other"),
        message_id=8,
    )

    def _update(chat_id: int, user_id: int, username: str, message_id: int):
        return SimpleNamespace(
            effective_message=SimpleNamespace(
                text="hi",
                caption="看图",
                message_id=message_id,
                reply_to_message=reply,
                photo=[SimpleNamespace(file_id="p")],
                document=SimpleNamespace(
                    file_id="d", file_name="a.txt", mime_type="text/plain"
                ),
            ),
            effective_chat=SimpleNamespace(id=chat_id, type="group"),
            effective_user=SimpleNamespace(id=user_id, username=username),
        )

    # A blacklisted member of the bound group, then a sender in an unbound chat.
    for update in [_update(-100, 5, "Troll", 1), _update(-200, 6, "friend", 2)]:
        await channel._on_message(update, context)
        await channel._on_photo(update, context)
        await channel._on_document(update, context)
        await channel._on_command(update, context)

    assert bus.inbound == []
    typing.assert_not_awaited()
    remember.assert_not_awaited()
    get_file.assert_not_awaited()
    await channel.stop()


class _PushTool:
    def __init__(self) -> None:
        self.registered: list[str] = []
        self.unregistered: list[str] = []

    def register_channel(self, name: str, **_kwargs: object) -> None:
        self.registered.append(name)

    def unregister_channel(self, name: str, **_kwargs: object) -> None:
        self.unregistered.append(name)


@pytest.mark.asyncio
async def test_plugin_channel_takes_runtime_state_and_commands_from_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """插件在 setup 时只有 token；bus、会话与 bot 命令都来自 ChannelHost 的 ctx。"""
    mod = _import_telegram_channel(monkeypatch)
    channel = mod.TelegramChannel(token="token")
    assert channel.name == "telegram"
    assert channel.configuration_key is None
    bus = _Bus()
    push_tool = _PushTool()
    hub = SimpleNamespace(name="hub")
    ctx = ChannelContext(
        bus=bus,  # type: ignore[arg-type]
        session_manager=_SessionManager(tmp_path),  # type: ignore[arg-type]
        event_bus=EventBus(),
        push_tool=push_tool,  # type: ignore[arg-type]
        attachment_store=SimpleNamespace(),  # type: ignore[arg-type]
        http_resources=SimpleNamespace(),  # type: ignore[arg-type]
        interrupt_controller=None,
        bot_commands=[("memorystatus", "查看记忆整理状态")],
        log=MagicMock(),
        channel_hub=hub,  # type: ignore[arg-type]
    )

    await channel.start(ctx)

    commands = channel._app.bot.set_my_commands.await_args.args[0]
    assert [cmd.command for cmd in commands] == ["memorystatus", "stop", "chatid"]
    assert channel._channel_hub is hub
    assert channel._attachments.create_path("x_", ".txt").parent == (
        tmp_path / "uploads"
    )
    assert bus.outbound == [("telegram", channel._on_response)]
    assert push_tool.registered == ["telegram"]
    await channel.stop()
    assert bus.outbound == []
    assert push_tool.unregistered == ["telegram"]


@pytest.mark.asyncio
async def test_telegram_chatid_reports_ids_without_role_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from agent.plugin_host.manifest import load_manifest

    mod = _import_telegram_channel(monkeypatch)
    manifest = load_manifest(Path(__file__).resolve().parents[1])
    assert manifest is not None
    bus = _Bus()
    role_store = RoleStore(tmp_path)
    role_store.create_role(role_id="mira", name="Mira", system_prompt="you are mira")
    role_store.update_role(
        "mira",
        channel_bindings=[
            {
                "channel": "telegram",
                "chat_id": "-100",
                "chat_type": "group",
                "blocked_senders": ["troll"],
            }
        ],
    )
    channel = mod.TelegramChannel(
        token="token",
        bus=bus,
        session_manager=_SessionManager(tmp_path),
        event_bus=EventBus(),
        chat_types=manifest.channel_chat_types("telegram"),
    )
    send = AsyncMock()
    monkeypatch.setattr(mod, "send_markdown", send)
    await channel.start()
    remember = AsyncMock()
    monkeypatch.setattr(channel, "_remember_username", remember)
    context = SimpleNamespace(bot=channel._app.bot)

    def _update(chat_id: int, chat_type: str, user_id: int, username: str):
        return SimpleNamespace(
            effective_message=SimpleNamespace(text="/chatid", message_id=1),
            effective_chat=SimpleNamespace(id=chat_id, type=chat_type),
            effective_user=SimpleNamespace(id=user_id, username=username),
        )

    # /chatid reports IDs before account ownership, even when old bindings exist.
    await channel._on_chat_id_command(_update(42, "private", 42, "me"), context)
    await channel._on_chat_id_command(_update(-200, "supergroup", 6, "a"), context)
    await channel._on_chat_id_command(_update(-100, "group", 7, "friend"), context)
    await channel._on_chat_id_command(_update(-100, "group", 5, "Troll"), context)

    assert [call.args[1:3] for call in send.await_args_list] == [
        ("42", "会话类型：私聊\n用户 ID：42"),
        ("-200", "会话类型：群聊\n群组 ID：-200"),
        ("-100", "会话类型：群聊\n群组 ID：-100"),
        ("-100", "会话类型：群聊\n群组 ID：-100"),
    ]
    assert bus.inbound == []
    remember.assert_not_awaited()
    await channel.stop()
