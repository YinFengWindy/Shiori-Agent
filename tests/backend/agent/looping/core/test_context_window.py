"""Host admission, actual scope, shared role gate, and command lifecycle isolation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from agent.config_models import ModelRegistration
from agent.core.passive_turn.reasoner import DefaultReasoner
from agent.looping.core.context_window import _ContextWindowMixin
from agent.looping.core.processing import _ProcessingMixin
from bus.event_bus import EventBus
from shiori_sdk.messages import InboundMessage
from bus.events_context import ContextWindowChanged
from bus.processing import ProcessingState
from conversation.service import desktop_thread_id
from shiori_sdk.channels.threads import network_thread_id
from core.roles.model_runtime import RoleModelRuntime
from core.roles.role_runtime import RoleRuntimeRegistry
from core.roles.services import RoleRepository
from core.roles.store import RoleStore
from desktop_bridge.request_dispatcher import BridgeRequestDispatcher
from session.manager import SessionManager


class _Harness(_ContextWindowMixin, _ProcessingMixin):
    pass


def _control(tmp_path, *, configured=True):
    roles = RoleStore(tmp_path)
    roles.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="fixed",
        runtime_config={"dialogue_model_registration_id": "model"},
    )
    models = RoleModelRuntime(
        default_max_tokens=8192,
        role_store=roles,
        registrations=(
            [
                ModelRegistration(
                    id="model",
                    provider="openai",
                    model="actual-selected",
                    api_key="test",
                    base_url="",
                    model_context_window=128000,
                )
            ]
            if configured
            else []
        ),
    )
    loop = _Harness()
    loop._role_runtime_registry = RoleRuntimeRegistry(
        RoleRepository(roles), model_resolver=models
    )
    loop.session_manager = SessionManager(tmp_path)
    loop._processing_state = ProcessingState()
    loop._event_bus = EventBus()
    loop.bus = SimpleNamespace(publish_outbound=AsyncMock())
    loop._reasoner = Mock(spec=DefaultReasoner)
    loop._reasoner.context_window = SimpleNamespace(
        inspect=AsyncMock(return_value={"reason": "no content", "result": None}),
        controller=SimpleNamespace(
            memory=SimpleNamespace(is_busy=lambda _: False), is_busy=lambda _: False
        ),
    )
    loop._active_tasks, loop._active_turn_states = {}, {}
    loop._core_runner = SimpleNamespace(
        process=AsyncMock(side_effect=AssertionError("command became conversation"))
    )
    return loop, models


def _msg(loop, *, thread=None, text="/compact"):
    context = loop._role_runtime_registry.create_context(
        role_id="mira",
        thread_id=thread or desktop_thread_id("mira"),
        transport_channel="qq",
        transport_chat_id="group-a",
        source="channel_hub",
        work_kind="passive_turn",
    )
    return InboundMessage(
        channel="qq",
        chat_id="group-a",
        sender="admitted-sender",
        content=text,
        metadata=context.to_metadata(),
    )


async def test_dispatcher_repeated_compact_rejects_while_first_holds_shared_role_gate(
    tmp_path,
):
    loop, models = _control(tmp_path)
    started, release = asyncio.Event(), asyncio.Event()
    events = []
    loop._event_bus.on(ContextWindowChanged, events.append)

    async def inspect(**kwargs):
        started.set()
        await release.wait()
        return {"result": None, "reason": "complete"}

    loop._reasoner.context_window.inspect.side_effect = inspect
    dispatcher = BridgeRequestDispatcher()
    replies = asyncio.Queue()

    async def compact():
        await replies.put(
            await loop.inspect_context_window(_msg(loop), "role:mira", compact=True)
        )

    try:
        dispatcher.submit({"method": "chat.context.compact"}, compact)
        await asyncio.wait_for(started.wait(), 1)
        dispatcher.submit({"method": "chat.context.compact"}, compact)
        rejected = await asyncio.wait_for(replies.get(), 1)
        assert rejected["busy"] and rejected["tokens"] is None
        assert loop._reasoner.context_window.inspect.await_count == 1
        release.set()
        await dispatcher.aclose()
        assert [event.busy for event in events] == [True, False]
        runtime = await loop._role_runtime_registry.get("mira")
        assert not runtime.busy
    finally:
        release.set()
        await dispatcher.aclose()
        await models.aclose()


async def test_command_uses_actual_external_thread_and_does_not_create_turn_or_change_task_owner(
    tmp_path,
):
    loop, models = _control(tmp_path)
    thread = network_thread_id("mira", "qq", "group-a")
    msg = _msg(loop, thread=thread, text=" /COMPACT@bot ")
    marker = object()
    loop._active_tasks["role:mira"] = marker
    try:
        reply = await loop.process_direct(
            msg.content,
            session_key="role:mira",
            channel="qq",
            chat_id="group-a",
            metadata=msg.metadata,
        )
        assert reply == "no content"
        request = loop._reasoner.context_window.inspect.await_args.kwargs
        assert request["context_view"].thread_id == thread
        assert request["context_view"].is_external
        assert loop._active_tasks["role:mira"] is marker
        assert not loop.session_manager.get_or_create("role:mira").messages
        loop._core_runner.process.assert_not_awaited()
        assert (
            await loop._compact_command(
                _msg(loop, text="/compact_status"), "role:mira", dispatch_outbound=False
            )
            is None
        )
    finally:
        await models.aclose()


async def test_missing_or_forged_role_scope_cannot_reach_controller(tmp_path):
    loop, models = _control(tmp_path)
    try:
        with pytest.raises(ValueError, match="角色与会话不匹配"):
            await loop.inspect_context_window(_msg(loop), "role:other", compact=True)
        with pytest.raises(ValueError, match="RoleExecutionContext"):
            await loop.inspect_context_window(
                InboundMessage(
                    channel="qq", chat_id="x", sender="s", content="/compact"
                ),
                "role:mira",
                compact=True,
            )
        loop._reasoner.context_window.inspect.assert_not_awaited()
    finally:
        await models.aclose()


async def test_incomplete_model_is_unknown_and_does_not_execute_provider(tmp_path):
    loop, models = _control(tmp_path, configured=False)
    try:
        status = await loop.inspect_context_window(_msg(loop), "role:mira")
        assert status["tokens"] is None and status["model_context_window"] is None
        assert not status["can_compact"] and "模型" in status["reason"]
        loop._reasoner.context_window.inspect.assert_not_awaited()
    finally:
        await models.aclose()
