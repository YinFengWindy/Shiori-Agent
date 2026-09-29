from __future__ import annotations

from datetime import datetime
from pathlib import Path

from conversation.service import ConversationService, LegacySessionDescriptor
from core.accounts import AccountRecord
from core.identity import IdentityChat, UserIdentityStore
from core.memory.group_environment import GroupEnvironment, GroupEnvironmentUpdate
from session.manager import SessionManager


def test_recent_activity_leaves_out_chats_merged_into_the_user_context(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    conversation = ConversationService(manager)
    environment = GroupEnvironment(tmp_path, manager.conversation_store)
    now = datetime.now().astimezone()
    thread_ids: dict[str, str] = {}
    for chat_id in ("902", "903"):
        thread = conversation.ensure_thread_for_session(
            LegacySessionDescriptor(
                session_key=f"qq:{chat_id}",
                role_id="mira",
                channel="qq",
                chat_id=chat_id,
            )
        )
        thread_ids[chat_id] = thread.id
        environment.apply(
            "mira",
            GroupEnvironmentUpdate(
                thread_id=thread.id,
                label=f"与「{chat_id}」的私聊",
                recent_activity=f"{chat_id} 的最近动态",
                group_note="",
            ),
            updated_at=now,
        )
    # 陌生私聊 902 绑定为用户本人后并入用户上下文。
    account = AccountRecord(
        id="qq:101",
        plugin_id="qq",
        platform="qq",
        platform_account_id="101",
        config_ref="101",
        role_id="mira",
    )
    identities = UserIdentityStore(tmp_path)
    assert identities.pair(
        identities.create_pairing_code().code,
        record=account,
        user_id="902",
        scope="platform",
        chat=IdentityChat(account.id, "qq", "902"),
    )

    injected = environment.render_recent_activity("mira", now=now)

    assert "903 的最近动态" in injected
    assert "902 的最近动态" not in injected
    # 记录本身不迁移、不删除。
    assert environment.read_recent_activity(thread_ids["902"]) == "902 的最近动态"
