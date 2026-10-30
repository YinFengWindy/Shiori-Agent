"""``HostAffectionSources``: the host facts the affection plugin reads."""

from __future__ import annotations

from pathlib import Path

from conversation.service import desktop_thread_id
from core.roles import RoleStore
from core.roles.affection_host import HostAffectionSources
from session.manager import SessionManager
from shiori_sdk.channels.threads import network_thread_id


def test_recent_user_messages_keep_only_the_users_own(tmp_path: Path) -> None:
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="you are mira")
    manager = SessionManager(tmp_path)
    sources = HostAffectionSources(
        workspace=tmp_path,
        role_store=roles,
        session_manager=manager,
        presence=manager.presence,
    )
    session = sources.get_session(sources.role_session_key("mira"))
    group = network_thread_id("mira", "qq", "gqq:7")
    session.add_message("user", "桌面里的你", thread_id=desktop_thread_id("mira"))
    session.add_message(
        "user",
        "群里的你",
        thread_id=group,
        metadata={"message_source": {"sender_id": "902", "sender_is_user": True}},
    )
    session.add_message(
        "user",
        "群友",
        thread_id=group,
        metadata={"message_source": {"sender_id": "555"}},
    )
    session.add_message("assistant", "回群友", thread_id=group)

    recent = sources.recent_user_messages("mira", list(session.messages))

    assert [item["content"] for item in recent] == ["桌面里的你", "群里的你"]
