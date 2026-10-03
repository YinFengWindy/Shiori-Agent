from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import asyncio
from unittest.mock import AsyncMock

import pytest

from agent.tools.message_push import MessagePushTool
from agent.turns.turn_pushes import TurnPushDrafts, current_turn_pushes
from bus.event_bus import EventBus
from bus.events_lifecycle import ExternalTextPushed, ProactiveMessageCommitted
from shiori_sdk.channels.threads import network_thread_id
from conversation.push_sync import ExternalPushSyncService
from conversation.context_scope import user_context_view
from core.identity import IdentityChat, UserIdentityStore
from shiori_sdk.accounts.models import AccountRecord
from session.manager import SessionManager


@pytest.mark.asyncio
async def test_pre_persisted_proactive_image_is_not_duplicated(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path)
    session = session_manager.open_role_session("mira", role_name="Mira")
    image = str(tmp_path / "scene.png")
    session.add_message(
        "assistant",
        "给你看张图",
        media=[image],
        proactive=True,
        metadata={
            "transport_channel": "telegram",
            "transport_chat_id": "123",
        },
    )
    await session_manager.append_messages(session, session.messages[-1:])
    event_bus = EventBus()
    _ = ExternalPushSyncService(
        live_turn_pushes=current_turn_pushes,
        session_manager=session_manager,
        event_bus=event_bus,
    )
    push_tool = MessagePushTool(event_bus=event_bus)

    async def send_image(_chat_id: str, _image: str) -> None:
        return None

    push_tool.register_channel("telegram", image=send_image)

    result = await push_tool.execute(
        channel="telegram",
        chat_id="123",
        image=image,
        role_id="mira",
        session_key="role:mira",
        push_message_already_persisted="true",
    )

    assert result == "图片已发送"
    assert len(session_manager.get_or_create("role:mira").messages) == 1


@pytest.mark.asyncio
async def test_pre_persisted_proactive_image_allows_retry_transport(
    tmp_path: Path,
) -> None:
    session_manager = SessionManager(tmp_path)
    session = session_manager.open_role_session("mira", role_name="Mira")
    image = str(tmp_path / "scene.png")
    session.add_message(
        "assistant",
        "给你看张图",
        media=[image],
        proactive=True,
        metadata={
            "source": "proactive",
            "transport_channel": "qqbot",
            "transport_chat_id": "primary",
        },
    )
    await session_manager.append_messages(session, session.messages[-1:])
    event_bus = EventBus()
    _ = ExternalPushSyncService(
        live_turn_pushes=current_turn_pushes,
        session_manager=session_manager,
        event_bus=event_bus,
    )
    push_tool = MessagePushTool(event_bus=event_bus)

    async def send_image(_chat_id: str, _image: str) -> None:
        return None

    push_tool.register_channel("telegram", image=send_image)

    result = await push_tool.execute(
        channel="telegram",
        chat_id="retry-target",
        image=image,
        role_id="mira",
        session_key="role:mira",
        push_message_already_persisted="true",
    )

    assert result == "图片已发送"
    assert len(session_manager.get_or_create("role:mira").messages) == 1


def _text_sync(tmp_path: Path):
    """A role session, the sync service on its bus, a QQ push tool, and the events seen."""
    session_manager = SessionManager(tmp_path)
    session_manager.open_role_session("mira", role_name="Mira")
    event_bus = EventBus()
    _ = ExternalPushSyncService(
        live_turn_pushes=current_turn_pushes,
        session_manager=session_manager,
        event_bus=event_bus,
    )
    committed: list[ProactiveMessageCommitted] = []
    texts: list[ExternalTextPushed] = []
    event_bus.on(ProactiveMessageCommitted, committed.append)
    event_bus.on(ExternalTextPushed, texts.append)
    push_tool = MessagePushTool(event_bus=event_bus)

    async def send_text(_chat_id: str, _text: str) -> str:
        return "qq-1"

    push_tool.register_channel("qq", text=send_text)
    return session_manager, push_tool, committed, texts


async def test_concurrent_delivery_events_commit_and_notify_only_once(
    tmp_path, monkeypatch
):
    manager = SessionManager(tmp_path)
    session = manager.open_role_session("mira", role_name="Mira")
    bus = EventBus()
    service = ExternalPushSyncService(
        live_turn_pushes=current_turn_pushes, session_manager=manager, event_bus=bus
    )
    committed = []
    bus.on(ProactiveMessageCommitted, committed.append)
    append = AsyncMock(wraps=manager._append_messages)
    monkeypatch.setattr(manager, "_append_messages", append)
    event = ExternalTextPushed(
        session_key=session.key,
        role_id="mira",
        channel="qq",
        chat_id="902",
        text="delivered once",
        delivery_key="scheduler:once",
    )
    tasks = []
    try:
        async with manager._lock(session.key):
            tasks = [
                asyncio.create_task(service.handle_text_pushed(event)) for _ in range(2)
            ]
            await asyncio.sleep(0)
            assert append.await_count == 2
            assert not any(task.done() for task in tasks)
            assert session.messages == []
        await asyncio.gather(*tasks)
        stored = manager._store.fetch_session_messages(session.key)
        assert len(stored) == 1
        assert [item.message_id for item in committed] == [stored[0]["id"]]
    finally:
        await asyncio.gather(*tasks, return_exceptions=True)
        await bus.aclose()


@pytest.mark.parametrize("kind", ["text", "image"])
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_abandoned_push_retains_the_admitted_turn_boundary(
    tmp_path, kind, failure
):
    manager, push, _, _ = _text_sync(tmp_path)
    push.register_channel(
        "qq", text=AsyncMock(return_value=None), image=AsyncMock(return_value=None)
    )
    old_start = "2026-01-01T00:00:00+00:00"
    drafts = TurnPushDrafts("role:mira", started_at=datetime.fromisoformat(old_start))
    with drafts.collect():
        await push.execute(
            channel="qq",
            chat_id="902",
            role_id="mira",
            session_key="role:mira",
            defer_push_session_sync="true",
            **(
                {"message": "old turn text"}
                if kind == "text"
                else {"image": "scene.png"}
            ),
        )
    # The draft already belongs to the old admitted turn; cleanup must preserve it.
    assert drafts.messages[0]["metadata"]["context_turn_started_at"] == old_start
    identities = UserIdentityStore(
        tmp_path, clock=lambda: datetime(2026, 1, 2, tzinfo=timezone.utc)
    )
    record = AccountRecord(
        id="qq:101",
        plugin_id="qq",
        platform="qq",
        platform_account_id="101",
        config_ref="101",
        role_id="mira",
    )
    assert identities.pair(
        identities.create_pairing_code().code,
        record=record,
        user_id="902",
        scope="platform",
        chat=IdentityChat(record.id, "qq", "902"),
    )
    view = user_context_view(tmp_path, "mira")
    assert not view.includes(drafts.messages[0])
    await drafts.abandoned(turn_error=failure("turn ended"))
    [stored] = manager._store.fetch_session_messages("role:mira")
    assert not view.includes(stored)
    assert stored["metadata"]["context_turn_started_at"] == old_start


@pytest.mark.asyncio
async def test_host_text_push_is_stored_once_under_the_chats_thread(
    tmp_path: Path,
) -> None:
    session_manager, push_tool, committed, _ = _text_sync(tmp_path)

    for _attempt in range(2):
        # A retried delivery carries the same key.
        await push_tool.execute(
            channel="qq",
            chat_id="gqq:5",
            message="该喝水啦",
            role_id="mira",
            session_key="role:mira",
            push_delivery_key="scheduler:job:1",
        )

    stored = session_manager._store.fetch_session_messages("role:mira")
    assert [
        (message["role"], message["content"], message["thread_id"])
        for message in stored
    ] == [("assistant", "该喝水啦", network_thread_id("mira", "qq", "gqq:5"))]
    assert stored[0]["metadata"]["delivery_key"] == "scheduler:job:1"
    assert [event.message_id for event in committed] == [stored[0]["id"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["text", "image"])
async def test_turn_push_waits_for_its_turn_and_is_kept_if_the_turn_fails(
    tmp_path: Path, kind: str
) -> None:
    session_manager, push_tool, committed, _ = _text_sync(tmp_path)
    sent = AsyncMock(return_value=None)
    push_tool.register_channel("qq", text=sent, image=sent)
    payload = {"message": "顺便说一声"} if kind == "text" else {"image": "scene.png"}
    expected = (
        payload.get("message", ""),
        [payload["image"]] if kind == "image" else None,
        network_thread_id("mira", "qq", "gqq:5"),
    )
    drafts = TurnPushDrafts("role:mira")

    with drafts.collect():
        await push_tool.execute(
            channel="qq",
            chat_id="gqq:5",
            role_id="mira",
            session_key="role:mira",
            defer_push_session_sync="true",
            **payload,
        )

    # Left to the turn's commit: nothing stored or announced yet.
    assert committed == []
    assert session_manager._store.fetch_session_messages("role:mira") == []
    assert [
        (draft["content"], draft.get("media"), draft["thread_id"])
        for draft in drafts.messages
    ] == [expected]

    # The turn never commits: the push it delivered is still recorded, once.
    await drafts.abandoned()
    await drafts.abandoned()
    stored = session_manager._store.fetch_session_messages("role:mira")
    assert [(row["content"], row.get("media"), row["thread_id"]) for row in stored] == [
        expected
    ]
    assert [event.message_id for event in committed] == [stored[0]["id"]]


@pytest.mark.asyncio
async def test_committed_turn_does_not_record_its_pushes_again(tmp_path: Path) -> None:
    session_manager, push_tool, _, _ = _text_sync(tmp_path)
    drafts = TurnPushDrafts("role:mira")
    with drafts.collect():
        await push_tool.execute(
            channel="qq",
            chat_id="gqq:5",
            message="顺便说一声",
            role_id="mira",
            session_key="role:mira",
            defer_push_session_sync="true",
        )

    await drafts.committed()
    await drafts.abandoned()

    assert session_manager._store.fetch_session_messages("role:mira") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["text", "image"])
async def test_push_from_a_turn_no_live_turn_owns_is_stored_in_the_role_session(
    tmp_path: Path, kind: str
) -> None:
    # A background task's report: the turn runs in the chat's own session.
    session_manager, push_tool, committed, _ = _text_sync(tmp_path)
    sent = AsyncMock(return_value=None)
    push_tool.register_channel("qq", text=sent, image=sent)
    payload = {"message": "报告完成"} if kind == "text" else {"image": "report.png"}

    result = await push_tool.execute(
        channel="qq",
        chat_id="gqq:5",
        role_id="mira",
        session_key="qq:gqq:5",
        defer_push_session_sync="true",
        **payload,
    )

    assert "已发送" in result
    sent.assert_awaited_once()
    stored = session_manager._store.fetch_session_messages("role:mira")
    assert [(row["content"], row.get("media"), row["thread_id"]) for row in stored] == [
        (
            payload.get("message", ""),
            [payload["image"]] if kind == "image" else None,
            network_thread_id("mira", "qq", "gqq:5"),
        )
    ]
    assert [event.session_key for event in committed] == ["role:mira"]


@pytest.mark.asyncio
async def test_a_failure_to_record_never_fails_the_delivered_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_manager, push_tool, _, _ = _text_sync(tmp_path)
    monkeypatch.setattr(
        session_manager, "append_messages", AsyncMock(side_effect=OSError("disk"))
    )

    result = await push_tool.execute(
        channel="qq",
        chat_id="gqq:5",
        message="该喝水啦",
        role_id="mira",
        session_key="role:mira",
    )

    assert result == "文本已发送"
