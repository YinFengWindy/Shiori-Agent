from __future__ import annotations

import asyncio

from core.roles.reply_state import RoleReply, RoleReplyContext

from typing import Any, cast
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.looping.ports import SessionServices
from agent.turns.orchestrator import TurnOrchestrator, TurnOrchestratorDeps
from agent.turns.outbound import (
    DeliveryReceipt,
    OutboundDispatch,
    OutboundDispatchError,
)
from agent.turns.result import TurnOutbound, TurnResult, TurnTrace
from session.manager import SessionManager
from bus.event_bus import EventBus
from bus.events_lifecycle import ProactiveMessageCommitted
from agent.tools.message_push import MessagePushTool
from agent.account_delivery import AccountDelivery, AccountSendReceipt
from core.accounts import AccountRegistry
from core.accounts.delivery_ledger import AccountDeliveryLedger
from agent.turns.outbound import PushToolOutboundPort
from conversation.push_sync import ExternalImageSyncService
from session.manager.models import build_session_message
from core.roles.reply_state import reply_state_metadata


class _DummySession:
    def __init__(self, key: str) -> None:
        self.key = key
        self.messages: list[dict[str, object]] = []
        self.metadata: dict[str, object] = {}
        self.last_consolidated = 0

    def add_message(self, role: str, content: str, media=None, **kwargs) -> None:
        msg: dict[str, object] = {
            "role": role,
            "content": content,
        }
        if media:
            msg["media"] = list(media)
        msg.update(kwargs)
        self.messages.append(msg)


@pytest.mark.asyncio
async def test_explicit_proactive_account_target_records_receipt_without_default_send(
    tmp_path,
) -> None:
    sender = SimpleNamespace(
        send=AsyncMock(
            return_value=AccountSendReceipt(
                attempt_id="attempt-1",
                account_id="account-1",
                target_kind="private",
                target_id="user-1",
                platform_message_id="platform-9",
                ownership_current=True,
            )
        )
    )
    default = SimpleNamespace(dispatch=AsyncMock())
    orchestrator = TurnOrchestrator(
        TurnOrchestratorDeps(
            session=SessionServices(session_manager=SessionManager(tmp_path)),
            outbound=default,
            account_delivery=sender,
        )
    )
    message: dict[str, Any] = {"metadata": {}}
    delivered = await orchestrator._deliver_before_commit(
        message,
        channel="desktop",
        chat_id="role:mira",
        content="hello",
        media=[],
        metadata={"role_id": "mira"},
        account_target={
            "account_id": "account-1",
            "target_kind": "private",
            "target_id": "user-1",
        },
    )
    assert delivered
    assert message["delivery_status"] == "sent"
    assert message["external_message_id"] == "platform-9"
    assert message["metadata"]["delivery_account_id"] == "account-1"
    assert message["metadata"]["delivery_attempt_id"] == "attempt-1"
    default.dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_proactive_target_remains_durable_without_turn_commit(
    tmp_path,
) -> None:
    accounts = AccountRegistry(tmp_path, lambda role_id: role_id == "mira")
    accounts.set_plugin_enabled("chat", True)
    account = accounts.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="bot",
        config_ref="bot",
        token="live",
    )
    account_id = account.record.id
    accounts.assign(account_id, "mira")
    accounts.report(account_id, "live", connection="online")

    async def rejected(payload):
        raise ValueError("target rejected")

    rpc = SimpleNamespace(resolve=lambda name: ("chat", rejected))
    ledger = AccountDeliveryLedger(tmp_path)
    delivery = AccountDelivery(accounts, rpc, ledger)
    default = SimpleNamespace(dispatch=AsyncMock())
    orchestrator = TurnOrchestrator(
        TurnOrchestratorDeps(
            session=SessionServices(session_manager=SessionManager(tmp_path)),
            outbound=default,
            account_delivery=delivery,
        )
    )
    with pytest.raises(ValueError, match="target rejected"):
        await orchestrator._deliver_before_commit(
            {"metadata": {}},
            channel="desktop",
            chat_id="role:mira",
            content="hello",
            media=[],
            metadata={"role_id": "mira"},
            account_target={
                "account_id": account_id,
                "target_kind": "private",
                "target_id": "opaque-user",
            },
        )
    [attempt] = AccountDeliveryLedger(tmp_path).list_for_role("mira")
    assert (attempt.account_id, attempt.target_id, attempt.source) == (
        account_id,
        "opaque-user",
        "proactive",
    )
    assert (attempt.status, attempt.error) == ("failed", "ValueError")
    default.dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_proactive_media_commit_notifies_shared_session(tmp_path) -> None:
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[],
    )

    def add_message(role: str, content: str, media=None, **kwargs) -> None:
        session.messages.append(
            {
                "role": role,
                "content": content,
                "media": list(media or []),
                **kwargs,
            }
        )

    session.add_message = add_message
    initial_metadata = dict(session.metadata)
    session_manager = SessionManager(tmp_path)
    session = session_manager.get_or_create(session.key)
    session.metadata.update(initial_metadata)

    dispatched: list[OutboundDispatch] = []

    class _Outbound:
        result: DeliveryReceipt | None = DeliveryReceipt.sent()

        async def dispatch(self, outbound: OutboundDispatch) -> DeliveryReceipt | None:
            dispatched.append(outbound)
            return self.result

    event_bus = EventBus()
    committed: list[ProactiveMessageCommitted] = []
    event_bus.on(ProactiveMessageCommitted, committed.append)
    outbound = _Outbound()
    orchestrator = TurnOrchestrator(
        TurnOrchestratorDeps(
            session=SessionServices(
                session_manager=cast(Any, session_manager),
                presence=None,
            ),
            outbound=outbound,
            event_bus=event_bus,
        )
    )

    result = TurnResult(
        role_reply=RoleReply("给你看张图", "平静", "我想和你聊聊。"),
        reply_context=RoleReplyContext(("平静",), ""),
        decision="reply",
        outbound=TurnOutbound(
            session_key="role:mira",
            content="给你看张图",
            media=["D:\\media\\scene.png"],
        ),
    )
    await orchestrator.handle_proactive_turn(
        result=result,
        session_key="role:mira",
        channel="telegram",
        chat_id="123",
    )

    assert session.messages[0]["media"] == ["D:\\media\\scene.png"]
    assert dispatched[0].media == ["D:\\media\\scene.png"]
    assert committed == [
        ProactiveMessageCommitted(
            session_key="role:mira",
            channel="telegram",
            role_id="mira",
            chat_id="123",
            assistant_response="给你看张图",
            tools_used=("message_push",),
        )
    ]

    result.reply_context = orchestrator.capture_reply_context("role:mira")
    outbound.result = None
    committed.clear()
    sent = await orchestrator.handle_proactive_turn(
        result=result,
        session_key="role:mira",
        channel="telegram",
        chat_id="123",
    )

    assert sent is False
    assert committed == []


@pytest.mark.asyncio
async def test_proactive_dispatch_error_is_not_converted_to_false(tmp_path) -> None:
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[],
    )

    def add_message(role: str, content: str, media=None, **kwargs) -> None:
        session.messages.append({"role": role, "content": content, **kwargs})

    session.add_message = add_message
    initial_metadata = dict(session.metadata)
    session_manager = SessionManager(tmp_path)
    session = session_manager.get_or_create(session.key)
    session.metadata.update(initial_metadata)

    class _Outbound:
        async def dispatch(self, outbound: OutboundDispatch) -> DeliveryReceipt | None:
            raise OutboundDispatchError(
                channel=outbound.channel,
                chat_id=outbound.chat_id,
                detail="network unavailable",
            )

    orchestrator = TurnOrchestrator(
        TurnOrchestratorDeps(
            session=SessionServices(
                session_manager=cast(Any, session_manager),
                presence=None,
            ),
            outbound=_Outbound(),
        )
    )
    failure_effect = SimpleNamespace(run=AsyncMock())

    with pytest.raises(OutboundDispatchError, match="network unavailable"):
        await orchestrator.handle_proactive_turn(
            result=TurnResult(
                role_reply=RoleReply("hello", "平静", "我想和你聊聊。"),
                reply_context=RoleReplyContext(("平静",), ""),
                decision="reply",
                outbound=TurnOutbound(session_key="role:mira", content="hello"),
                failure_side_effects=[failure_effect],
            ),
            session_key="role:mira",
            channel="telegram",
            chat_id="123",
        )

    failure_effect.run.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_orchestrator_skip_runs_side_effects_without_dispatch():
    order: list[str] = []

    class _Effect:
        async def run(self) -> None:
            order.append("side_effect")

    class _Outbound:
        async def dispatch(self, outbound: OutboundDispatch) -> DeliveryReceipt | None:
            order.append("dispatch")
            return DeliveryReceipt.sent()

    orchestrator = TurnOrchestrator(
        TurnOrchestratorDeps(
            session=SessionServices(
                session_manager=cast(
                    Any,
                    SimpleNamespace(
                        get_or_create=lambda _key: _DummySession("telegram:123")
                    ),
                ),
                presence=None,
            ),
            outbound=_Outbound(),
        )
    )

    sent = await orchestrator.handle_proactive_turn(
        result=TurnResult(
            decision="skip",
            outbound=None,
            trace=TurnTrace(source="proactive", extra={"skip_reason": "quiet_hours"}),
            side_effects=[_Effect()],
        ),
        session_key="telegram:123",
        channel="telegram",
        chat_id="123",
    )

    assert sent is False
    assert order == ["side_effect"]


@pytest.mark.asyncio
async def test_orchestrator_proactive_reply_persists_dispatches_and_runs_success_effects(
    tmp_path,
):
    order: list[str] = []
    session = _DummySession("telegram:123")

    class _Effect:
        def __init__(self, name: str) -> None:
            self._name = name

        async def run(self) -> None:
            order.append(self._name)

    class _Outbound:
        async def dispatch(self, outbound: OutboundDispatch) -> DeliveryReceipt | None:
            order.append("dispatch")
            assert outbound.content == "hello"
            return DeliveryReceipt.sent()

    presence = SimpleNamespace(
        record_proactive_sent=lambda _key: order.append("presence")
    )
    initial_metadata = dict(session.metadata)
    session_manager = SessionManager(tmp_path)
    session = session_manager.get_or_create(session.key)
    session.metadata.update(initial_metadata)
    orchestrator = TurnOrchestrator(
        TurnOrchestratorDeps(
            session=SessionServices(
                session_manager=cast(Any, session_manager),
                presence=cast(Any, presence),
            ),
            outbound=_Outbound(),
        )
    )

    sent = await orchestrator.handle_proactive_turn(
        result=TurnResult(
            role_reply=RoleReply("hello", "平静", "我想和你聊聊。"),
            reply_context=RoleReplyContext(("平静",), ""),
            decision="reply",
            outbound=TurnOutbound(session_key="telegram:123", content="hello"),
            evidence=["feed:1"],
            trace=TurnTrace(
                source="proactive",
                extra={
                    "tools_used": ["web_search"],
                    "tool_chain": [{"text": "", "calls": []}],
                    "steps_taken": 2,
                },
            ),
            side_effects=[_Effect("side_effect")],
            success_side_effects=[_Effect("success_effect")],
            failure_side_effects=[_Effect("failure_effect")],
        ),
        session_key="telegram:123",
        channel="telegram",
        chat_id="123",
    )

    assert sent is True
    assert session.messages[0]["proactive"] is True
    assert session.messages[0]["content"] == "hello"
    assert order == ["side_effect", "dispatch", "presence", "success_effect"]


@pytest.mark.asyncio
async def test_orchestrator_proactive_reply_records_presence_by_role_when_available(
    tmp_path,
):
    session = _DummySession("role:mira")
    session.metadata["role_id"] = "mira"
    calls: list[tuple[str, str]] = []

    class _Outbound:
        async def dispatch(self, outbound: OutboundDispatch) -> DeliveryReceipt | None:
            return DeliveryReceipt.sent()

    presence = SimpleNamespace(
        record_proactive_sent=lambda _key: calls.append(("session", _key)),
        record_proactive_sent_by_role=lambda role_id: calls.append(("role", role_id)),
    )
    initial_metadata = dict(session.metadata)
    session_manager = SessionManager(tmp_path)
    session = session_manager.get_or_create(session.key)
    session.metadata.update(initial_metadata)
    orchestrator = TurnOrchestrator(
        TurnOrchestratorDeps(
            session=SessionServices(
                session_manager=cast(Any, session_manager),
                presence=cast(Any, presence),
            ),
            outbound=_Outbound(),
        )
    )

    sent = await orchestrator.handle_proactive_turn(
        result=TurnResult(
            role_reply=RoleReply("hello", "平静", "我想和你聊聊。"),
            reply_context=RoleReplyContext(("平静",), ""),
            decision="reply",
            outbound=TurnOutbound(session_key="role:mira", content="hello"),
        ),
        session_key="role:mira",
        channel="telegram",
        chat_id="123",
    )

    assert sent is True
    assert calls == [("role", "mira")]


def _formal_result(owner, content="hello", media=None):
    return TurnResult(
        decision="reply",
        outbound=TurnOutbound("role:mira", content, media or []),
        role_reply=RoleReply(content, "平静", "我想和你聊聊。"),
        reply_context=owner.capture_reply_context("role:mira"),
    )


async def _send(owner, result):
    return await owner.handle_proactive_turn(
        result=result, session_key="role:mira", channel="telegram", chat_id="123"
    )


@pytest.mark.asyncio
async def test_successive_proactive_commits_keep_one_state_per_reply(
    tmp_path,
):
    sessions = SessionManager(tmp_path)
    sessions.open_role_session(
        "mira", role_name="Mira", role_runtime_config={"mood_catalog": ["平静", "开心"]}
    )
    outbound = SimpleNamespace(dispatch=AsyncMock(return_value=DeliveryReceipt.sent()))
    owner = TurnOrchestrator(TurnOrchestratorDeps(SessionServices(sessions), outbound))
    first = _formal_result(owner)
    assert await _send(owner, first)
    session = sessions.get_or_create("role:mira")
    first_stamp = session.metadata["current_mood_updated_at"]
    second = _formal_result(owner, "next")
    second.role_reply = RoleReply("next", "开心", "我很开心又见到你。")
    assert await _send(owner, second)
    metadata = dict(session.metadata)
    assert metadata["current_mood_updated_at"] != first_stamp
    assert len(session.messages) == 2
    assert session.metadata == metadata
    assert metadata["current_mood"] == "开心"
    assert metadata["current_thought"] == "我很开心又见到你。"
    for message, expected in zip(
        session.messages, [first.role_reply, second.role_reply], strict=True
    ):
        assert expected is not None
        assert message["metadata"]["mood"] == expected.mood
        assert message["metadata"]["thought"] == expected.thought
        assert "thought" not in message
    reloaded = SessionManager(tmp_path).get_or_create(session.key)
    assert reloaded.metadata == metadata
    assert len(reloaded.messages) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["false", "exception", "cancel", "projection"])
async def test_failed_proactive_delivery_does_not_publish_messages_or_state(
    tmp_path, monkeypatch, failure
):
    sessions = SessionManager(tmp_path)
    session = sessions.open_role_session("mira", role_name="Mira")
    sessions.save(session)
    previous = dict(session.metadata)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def dispatch(_outbound):
        entered.set()
        assert session.messages == []
        assert session.metadata == previous
        if failure == "cancel":
            await release.wait()
        if failure == "exception":
            raise OutboundDispatchError(
                channel="telegram", chat_id="123", detail="network"
            )
        return None if failure == "false" else DeliveryReceipt.sent()

    owner = TurnOrchestrator(
        TurnOrchestratorDeps(
            SessionServices(sessions), SimpleNamespace(dispatch=dispatch)
        )
    )
    if failure == "projection":

        def fail_projection(_session):
            raise RuntimeError("projection failed")

        monkeypatch.setattr(sessions, "_project_session_threads", fail_projection)
    failure_effect = AsyncMock()
    result = _formal_result(owner)
    result.failure_side_effects = [SimpleNamespace(run=failure_effect)]
    task = asyncio.create_task(_send(owner, result))
    await entered.wait()
    if failure == "cancel":
        # A queued save cannot see private drafts while delivery is outstanding.
        await sessions.save_async(session)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    elif failure == "false":
        assert await task is False
    else:
        with pytest.raises(RuntimeError):
            await task
    assert session.metadata == previous
    assert session.messages == []
    fresh = SessionManager(tmp_path).get_or_create(session.key)
    assert fresh.metadata == previous
    assert fresh.messages == []
    assert failure_effect.await_count == (0 if failure == "cancel" else 1)


@pytest.mark.asyncio
async def test_passive_commit_waits_for_delivery_and_stale_generation_cannot_overwrite(
    tmp_path,
):
    sessions = SessionManager(tmp_path)
    session = sessions.open_role_session("mira", role_name="Mira")
    entered, release = asyncio.Event(), asyncio.Event()

    async def dispatch(_outbound):
        entered.set()
        await release.wait()
        return DeliveryReceipt.sent()

    owner = TurnOrchestrator(
        TurnOrchestratorDeps(
            SessionServices(sessions), SimpleNamespace(dispatch=dispatch)
        )
    )
    result = _formal_result(owner)
    proactive = asyncio.create_task(_send(owner, result))
    await entered.wait()
    passive = asyncio.create_task(
        sessions.append_messages(
            session,
            [build_session_message("assistant", "old passive")],
            pending_messages=True,
            expected_mood_updated_at="",
            metadata_updates=reply_state_metadata(
                RoleReply("old passive", "平静", "我也想聊聊。"), updated_at="old"
            ),
        )
    )
    await asyncio.sleep(0)
    assert not passive.done()
    release.set()
    assert await proactive
    with pytest.raises(ValueError, match="过时"):
        await passive
    assert [m["content"] for m in session.messages] == ["hello"]
    with pytest.raises(ValueError, match="过时"):
        await _send(owner, result)
    assert len(session.messages) == 1
    current_stamp = str(session.metadata["current_mood_updated_at"])
    await sessions.append_messages(
        session,
        [build_session_message("assistant", "new passive")],
        pending_messages=True,
        expected_mood_updated_at=current_stamp,
        metadata_updates=reply_state_metadata(
            RoleReply("new passive", "平静", "我已经收到你的回应。"), updated_at="new"
        ),
    )
    assert session.metadata["current_thought"] == "我已经收到你的回应。"
    assert [m["content"] for m in session.messages] == ["hello", "new passive"]


@pytest.mark.asyncio
async def test_image_transport_lock_and_formal_delivery_do_not_deadlock(tmp_path):
    sessions = SessionManager(tmp_path)
    session = sessions.open_role_session("mira", role_name="Mira")
    bus = EventBus()
    ExternalImageSyncService(session_manager=sessions, event_bus=bus)
    push = MessagePushTool(event_bus=bus)
    push.set_transport_lock(asyncio.Lock())
    image_started, release_image, formal_started = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )

    async def image_sender(_chat_id, _image):
        image_started.set()
        await release_image.wait()

    push.register_channel(
        "telegram", text=AsyncMock(return_value=None), image=image_sender
    )
    port = PushToolOutboundPort(push, execution_context={"role_id": "mira"})

    async def formal_dispatch(outbound):
        formal_started.set()
        return await port.dispatch(outbound)

    owner = TurnOrchestrator(
        TurnOrchestratorDeps(
            SessionServices(sessions), SimpleNamespace(dispatch=formal_dispatch)
        )
    )
    external = asyncio.create_task(
        push.execute(
            channel="telegram",
            chat_id="123",
            image="/tmp/old.png",
            role_id="mira",
            session_key=session.key,
        )
    )
    await image_started.wait()
    formal = asyncio.create_task(
        _send(owner, _formal_result(owner, media=["/tmp/new.png"]))
    )
    await formal_started.wait()
    release_image.set()
    results = await asyncio.wait_for(asyncio.gather(external, formal), timeout=2)
    assert results[1] is True
    assert [m["media"] for m in session.messages] == [
        ["/tmp/old.png"],
        ["/tmp/new.png"],
    ]
    assert (
        session.messages[-1]["metadata"]["thought"]
        == session.metadata["current_thought"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["unsent text", ""])
async def test_image_only_channel_cannot_commit_requested_text(tmp_path, content):
    sessions = SessionManager(tmp_path)
    session = sessions.open_role_session("mira", role_name="Mira")
    sessions.save(session)
    previous_metadata = dict(session.metadata)
    push = MessagePushTool()
    image_sender = AsyncMock(return_value=None)
    push.register_channel("telegram", image=image_sender)
    owner = TurnOrchestrator(
        TurnOrchestratorDeps(
            SessionServices(sessions),
            PushToolOutboundPort(push, execution_context={"role_id": "mira"}),
        )
    )
    result = _formal_result(owner, content=content, media=["/tmp/cat.png"])

    if content:
        with pytest.raises(OutboundDispatchError, match="不支持发送文本"):
            await _send(owner, result)
        image_sender.assert_not_awaited()
        assert session.messages == []
        assert session.metadata == previous_metadata
        reloaded = SessionManager(tmp_path).get_or_create(session.key)
        assert reloaded.messages == []
        assert reloaded.metadata == previous_metadata
    else:
        assert await _send(owner, result)
        image_sender.assert_awaited_once_with("123", "/tmp/cat.png")
        assert session.messages[0]["content"] == ""
        assert session.messages[0]["media"] == ["/tmp/cat.png"]
        assert session.metadata["current_mood"] == "平静"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sender_result", "expected_external_id"),
    [("qqbot-msg-1", "qqbot-msg-1"), (None, None)],
)
async def test_proactive_push_records_delivery_on_the_committed_message(
    tmp_path, sender_result, expected_external_id
):
    sessions = SessionManager(tmp_path)
    session = sessions.open_role_session("mira", role_name="Mira")
    sessions.save(session)
    push = MessagePushTool()
    text_sender = AsyncMock(return_value=sender_result)
    push.register_channel("qqbot", text=text_sender)
    owner = TurnOrchestrator(
        TurnOrchestratorDeps(
            SessionServices(sessions),
            PushToolOutboundPort(push, execution_context={"role_id": "mira"}),
        )
    )

    assert await owner.handle_proactive_turn(
        result=_formal_result(owner),
        session_key="role:mira",
        channel="qqbot",
        chat_id="c2c:user-1",
    )

    text_sender.assert_awaited_once_with("c2c:user-1", "hello")
    # The row written by the commit itself carries the delivery facts; a reload
    # proves they reached the store, not just the in-memory draft.
    [row] = SessionManager(tmp_path)._store.fetch_session_messages("role:mira")
    assert row["content"] == "hello"
    assert row["delivery_status"] == "sent"
    assert row.get("external_message_id") == expected_external_id
    assert session.messages[0]["delivery_status"] == "sent"


@pytest.mark.asyncio
async def test_refused_proactive_push_commits_no_delivery_record(tmp_path):
    sessions = SessionManager(tmp_path)
    session = sessions.open_role_session("mira", role_name="Mira")
    sessions.save(session)
    outbound = SimpleNamespace(dispatch=AsyncMock(return_value=None))
    owner = TurnOrchestrator(TurnOrchestratorDeps(SessionServices(sessions), outbound))

    assert await _send(owner, _formal_result(owner)) is False

    assert session.messages == []
    assert sessions._store.fetch_session_messages("role:mira") == []


@pytest.mark.asyncio
async def test_queued_receipt_commits_without_claiming_delivery(tmp_path):
    sessions = SessionManager(tmp_path)
    session = sessions.open_role_session("mira", role_name="Mira")
    sessions.save(session)
    # A queue hand-off (the bus port) proves nothing reached the platform.
    outbound = SimpleNamespace(
        dispatch=AsyncMock(return_value=DeliveryReceipt.queued())
    )
    owner = TurnOrchestrator(TurnOrchestratorDeps(SessionServices(sessions), outbound))

    assert await _send(owner, _formal_result(owner)) is True

    [row] = sessions._store.fetch_session_messages("role:mira")
    assert row["content"] == "hello"
    assert "delivery_status" not in row
    assert "delivery_status" not in session.messages[0]
