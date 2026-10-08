import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from conversation.service import ConversationService
from desktop_bridge.app_service import DesktopAppService
from session.manager import SessionManager


def _push_service(tmp_path):
    manager = SessionManager(tmp_path)
    presence = Mock()
    relationship = Mock()
    relationship.enrich_session_metadata.side_effect = lambda metadata: metadata
    service = DesktopAppService(
        role_service=SimpleNamespace(),
        session_manager=manager,
        conversation_service=ConversationService(manager),
        presence=presence,
        relationship_runtime=relationship,
    )
    return service, manager, presence, relationship


@pytest.mark.parametrize("proactive", [False, True])
async def test_push_intent_survives_reload_and_deduplication(tmp_path, proactive):
    service, manager, presence, relationship = _push_service(tmp_path)

    _, first = await service.apply_desktop_push(
        "role:mira", media=["cg.png"], proactive=proactive
    )
    _, duplicate = await service.apply_desktop_push(
        "role:mira", media=["cg.png"], proactive=proactive
    )

    assert duplicate is first
    [stored] = SessionManager(tmp_path).get_or_create("role:mira").messages
    assert stored["proactive"] is proactive
    assert stored["media"] == ["cg.png"]
    assert presence.record_proactive_sent.call_count == int(proactive)
    assert relationship.handle_proactive_sent.call_count == int(proactive)
    assert manager.conversation_store.get_thread_by_legacy_session_key("role:mira")


@pytest.mark.parametrize("stored_intent", [False, True])
async def test_persisted_push_uses_its_original_intent(tmp_path, stored_intent):
    service, manager, presence, relationship = _push_service(tmp_path)
    session = manager.get_or_create("role:mira")
    session.add_message(
        "assistant",
        "",
        media=["cg.png"],
        proactive=stored_intent,
        metadata={"delivery_key": "original"},
    )
    await manager.save_async(session)

    _, delivered = await service.apply_desktop_push(
        session.key,
        media=["cg.png"],
        delivery_key="original",
        already_persisted=True,
        proactive=not stored_intent,
    )

    assert delivered["proactive"] is stored_intent
    assert len(session.messages) == 1
    assert presence.record_proactive_sent.call_count == int(stored_intent)
    assert relationship.handle_proactive_sent.call_count == int(stored_intent)


async def test_same_image_with_different_intent_is_not_deduplicated(tmp_path):
    service, manager, presence, _ = _push_service(tmp_path)
    for proactive in (False, True):
        await service.apply_desktop_push(
            "role:mira", media=["cg.png"], proactive=proactive
        )

    assert [m["proactive"] for m in manager.get_or_create("role:mira").messages] == [
        False,
        True,
    ]
    presence.record_proactive_sent.assert_called_once_with("role:mira")


async def test_supplemental_push_is_not_deduplicated_against_a_passive_reply(tmp_path):
    service, manager, _, _ = _push_service(tmp_path)
    session = manager.get_or_create("role:mira")
    session.add_message("assistant", "", media=["cg.png"])
    await manager.save_async(session)
    passive_message = session.messages[0]

    _, pushed = await service.apply_desktop_push(
        session.key, media=["cg.png"], proactive=False
    )

    assert pushed["id"] != passive_message["id"]
    assert len(session.messages) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message,media",
    [
        ("", None),
        (" \t\n", []),
        ("", ["   "]),
        (" ", ["", "\t", "\n"]),
    ],
)
async def test_empty_push_has_no_session_or_runtime_side_effects(
    tmp_path, message, media
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.add_message("assistant", "existing history")
    await manager.save_async(session)
    before = list(session.messages)
    updated_at = session.updated_at
    presence = Mock()
    relationship = Mock()
    conversation = Mock()
    service = DesktopAppService(
        role_service=SimpleNamespace(),
        session_manager=manager,
        conversation_service=conversation,
        presence=presence,
        relationship_runtime=relationship,
    )

    for chat_id in ("role:mira", "role:new"):
        with pytest.raises(ValueError, match="非空"):
            await service.apply_desktop_push(chat_id, message=message, media=media)

    assert session.messages == before
    assert session.updated_at == updated_at
    assert "role:new" not in manager._cache
    assert presence.mock_calls == []
    assert relationship.mock_calls == []
    assert conversation.mock_calls == []
    reloaded = SessionManager(tmp_path)
    assert reloaded.get_or_create("role:mira").messages == before
    assert not reloaded._store.session_exists("role:new")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message,media,expected_media",
    [
        ("  hello\n", [" "], None),
        ("", [" ", "image.png", "\t"], ["image.png"]),
        ("caption", ["document.pdf"], ["document.pdf"]),
    ],
)
async def test_push_with_content_survives_reload(
    tmp_path, message, media, expected_media
):
    manager = SessionManager(tmp_path)
    service = DesktopAppService(
        role_service=SimpleNamespace(),
        session_manager=manager,
        conversation_service=ConversationService(manager),
    )

    await service.apply_desktop_push("role:mira", message=message, media=media)

    reloaded = SessionManager(tmp_path).get_or_create("role:mira")
    assert len(reloaded.messages) == 1
    assert reloaded.messages[0]["content"] == message
    assert reloaded.messages[0].get("media") == expected_media


@pytest.mark.asyncio
@pytest.mark.parametrize("pause_at", ["append_messages", "save_async"])
async def test_persist_user_message_keeps_identity_across_concurrent_append(
    tmp_path,
    monkeypatch,
    pause_at,
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    presence = Mock()
    relationship = Mock()
    relationship.enrich_session_metadata.return_value = {"relationship": "updated"}
    service = DesktopAppService(
        role_service=SimpleNamespace(),
        session_manager=manager,
        conversation_service=ConversationService(manager),
        presence=presence,
        relationship_runtime=relationship,
    )
    entered = asyncio.Event()
    resume = asyncio.Event()
    original_operation = getattr(manager, pause_at)
    append_messages = manager.append_messages

    async def paused_operation(*args):
        # Inject a scheduling boundary; this tests the async return contract,
        # without assuming the default persistence implementation yields here.
        entered.set()
        await resume.wait()
        await original_operation(*args)

    monkeypatch.setattr(manager, pause_at, paused_operation)
    task = asyncio.create_task(
        service.persist_desktop_user_message(
            session=session,
            role_id="mira",
            content="my message",
            media=["photo.png"],
            metadata={"client_message_id": "client-user", "turn_id": "turn-user"},
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        user_message = session.messages[0]
        assert not task.done()
        session.add_message("assistant", "proactive reply", proactive=True)
        assistant_message = session.messages[-1]
        await append_messages(session, [assistant_message])
        resume.set()
        persisted = await asyncio.wait_for(task, timeout=2)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert persisted is user_message
    assert persisted["id"] != assistant_message["id"]
    assert isinstance(persisted["seq"], int)
    assert persisted["role"] == "user"
    assert persisted["content"] == "my message"
    assert persisted["media"] == ["photo.png"]
    assert persisted["metadata"]["client_message_id"] == "client-user"
    assert persisted["metadata"]["turn_id"] == "turn-user"
    presence.record_user_message.assert_called_once_with(session.key)
    relationship.handle_user_message.assert_called_once_with(session.key)
    reloaded = SessionManager(tmp_path).get_or_create(session.key)
    assert reloaded.metadata["relationship"] == "updated"
    assert {message["id"] for message in reloaded.messages} == {
        persisted["id"],
        assistant_message["id"],
    }
