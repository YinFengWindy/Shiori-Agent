"""Historical session ownership survives the account cutover and restart."""

from __future__ import annotations

from conversation.service import ConversationService, LegacySessionDescriptor
from core.roles.store import RoleStore
from session.manager import SessionManager


def test_lazy_legacy_thread_projection_after_binding_retirement(tmp_path):
    sessions = SessionManager(tmp_path)
    old = sessions.get_or_create("qq:gqq:42")
    old.add_message("user", "old group message")
    sessions.save(old)
    store = RoleStore(tmp_path)
    store.create_role(role_id="mira", name="Mira", system_prompt="Mira")
    store.update_role(
        "mira",
        channel_bindings=[
            {
                "channel": "qq",
                "chat_id": "gqq:42",
                "chat_type": "group",
                "blocked_senders": [],
            }
        ],
    )
    store.accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="100",
        config_ref="legacy",
        token="live",
    )
    assert store.get_role("mira").channel_bindings == []
    projected = sessions.conversation_store.get_thread_by_legacy_session_key(
        "qq:gqq:42"
    )
    assert projected is not None
    assert projected.role_id == "mira"

    restarted = RoleStore(tmp_path)
    conversations = ConversationService(
        SessionManager(tmp_path),
        binding_resolver=restarted.resolve_legacy_session_owner,
    )
    thread = conversations.ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="qq:gqq:42", role_id="", channel="qq", chat_id="gqq:42"
        )
    )
    assert thread.role_id == "mira"
    assert thread.channel == "qq"
    assert thread.external_thread_id == "gqq:42"
    assert conversations.get_thread_by_session_key("qq:gqq:42") == thread
