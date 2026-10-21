"""Turn start events retain transport identity without requiring it."""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from shiori_sdk.messages import InboundMessage
from shiori_sdk.channel_events import TurnStarted
from agent.looping.interrupt import turn_tracking_key


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata", [{"external_message_id": "source-1"}, {}])
async def test_turn_started_carries_originating_external_message_id(metadata):
    loop = object.__new__(AgentLoop)
    loop._event_bus = EventBus()
    observed: list[TurnStarted] = []

    async def observe(event: TurnStarted):
        observed.append(event)

    loop._event_bus.on(TurnStarted, observe)
    message = InboundMessage("qqbot", "user", "c2c:user", "hello", metadata=metadata)
    await loop._observe_turn_started(message, "role:mira")
    [event] = observed
    assert event.external_message_id == metadata.get("external_message_id", "")
    assert event.session_key == "role:mira"
    assert event.timestamp == message.timestamp


async def test_two_chats_keep_progress_and_explicit_stop_separate():
    loop = object.__new__(AgentLoop)
    loop._active_turn_states = {}
    loop._active_tasks = {}
    loop._interrupt_states = {}
    loop._compact_command = AsyncMock(return_value=None)
    entered = {chat: asyncio.Event() for chat in ("a", "b")}
    release = asyncio.Event()

    async def process(item, key):
        loop._append_partial_thinking(key, item.chat_id)
        entered[item.chat_id].set()
        await release.wait()

    loop._process_role_scoped = process
    tasks = [
        asyncio.create_task(
            loop.process_inbound(
                InboundMessage(
                    "qqbot",
                    "user",
                    chat,
                    chat,
                    metadata={"session_key_override": "role:mira"},
                )
            )
        )
        for chat in ("a", "b")
    ]
    await asyncio.gather(*(event.wait() for event in entered.values()))
    assert loop.request_interrupt("role:mira").status == "idle"
    stopped = loop.request_interrupt("role:mira", channel="qqbot", chat_id="a")
    assert stopped.state.partial_thinking == "a"
    await tasks[0]
    assert not tasks[1].done()
    assert (
        loop._active_turn_states[
            turn_tracking_key("role:mira", "qqbot", "b")
        ].partial_thinking
        == "b"
    )
    assert loop.request_interrupt("role:mira").status == "interrupted"
    await tasks[1]
    assert loop._active_turn_states == {}


@pytest.mark.parametrize(
    "stop_origin",
    [
        {"account_id": "telegram:other"},
        {"message_thread_id": 22},
        {"message_thread_id": None},
        {"chat_type": "private"},
        {"channel": "telegram_other"},
        {"chat_id": "other-chat"},
        {"session_key": "role:other"},
    ],
)
async def test_telegram_stop_requires_exact_origin_even_with_one_active_turn(
    monkeypatch, stop_origin
):
    from bootstrap.runtime.dispatcher import RuntimeDispatcher
    from plugins.telegram.backend.channel.commands import _CommandMixin

    loop = object.__new__(AgentLoop)
    loop._active_turn_states = {}
    loop._active_tasks = {}
    loop._interrupt_states = {}
    loop._compact_command = AsyncMock(return_value=None)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def process(item, key):
        loop._append_partial_thinking(key, "only this topic")
        entered.set()
        await release.wait()

    loop._process_role_scoped = process
    task = asyncio.create_task(
        loop.process_inbound(
            InboundMessage(
                "telegram_one",
                "user",
                "shared-chat",
                "hello",
                metadata={
                    "session_key_override": "role:mira",
                    "account_id": "telegram:one",
                    "chat_type": "supergroup",
                    "message_thread_id": 11,
                },
            )
        )
    )
    await entered.wait()
    send = AsyncMock()
    monkeypatch.setattr(
        "plugins.telegram.backend.channel.commands._call_send_markdown", send
    )
    controller = RuntimeDispatcher(SimpleNamespace(agent_loop=loop))

    async def stop(**changes):
        origin = {
            "account_id": "telegram:one",
            "message_thread_id": 11,
            "chat_type": "supergroup",
            "channel": "telegram_one",
            "chat_id": "shared-chat",
            "session_key": "role:mira",
            **changes,
        }
        channel = SimpleNamespace(
            _channel=origin["channel"],
            _account_id=origin["account_id"],
            _remember_chat=Mock(),
            _is_sender_admitted=Mock(return_value=True),
            _interrupt_controller=controller,
            _channel_hub=SimpleNamespace(
                resolve_account_runtime_session_key=lambda _: origin["session_key"]
            ),
            _app=SimpleNamespace(bot=Mock()),
            _telegram_outbound_limiter=None,
        )
        await _CommandMixin._on_stop_command(
            channel,
            SimpleNamespace(
                effective_message=SimpleNamespace(
                    text="/stop",
                    message_id=99,
                    message_thread_id=origin["message_thread_id"],
                ),
                effective_chat=SimpleNamespace(
                    id=origin["chat_id"], type=origin["chat_type"]
                ),
                effective_user=SimpleNamespace(id=42, username="Alice"),
            ),
            Mock(),
        )

    try:
        await stop(**stop_origin)
        assert send.await_args.args[2] == "当前没有正在执行的任务。"
        assert not task.done()
        assert not loop._interrupt_states
        # An underspecified legacy request cannot broaden into an account/topic.
        assert loop.request_interrupt("role:mira").status == "idle"
        assert (
            loop.request_interrupt(
                "role:mira", channel="telegram_one", chat_id="shared-chat"
            ).status
            == "idle"
        )
        await stop()
        await task
        assert send.await_args.args[2].startswith("本轮已中断")
        [state] = loop._interrupt_states.values()
        assert state.partial_thinking == "only this topic"
        assert state.original_metadata["message_thread_id"] == 11
    finally:
        release.set()
        await task
