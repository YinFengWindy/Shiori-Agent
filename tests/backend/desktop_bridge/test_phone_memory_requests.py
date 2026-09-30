"""The phone's chat info page reads and edits what the role remembers about one
external conversation and the members it met there."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from conversation.models import ThreadRecord
from conversation.service import ConversationService, LegacySessionDescriptor
from core.accounts import AccountRegistry
from core.identity import IdentityChat, UserIdentityStore
from core.memory.external_writes import ExternalLayerSnapshot, commit_external_layers
from core.memory.group_environment import GroupEnvironment, GroupEnvironmentUpdate
from core.memory.member_profiles import MemberKey, MemberProfile, MemberProfiles
from desktop_bridge.phone_memory_requests import DesktopPhoneMemoryRequestHandler
from session.manager import SessionManager


def _thread(conversation: ConversationService, *, role_id: str, chat_id: str):
    return conversation.ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key=f"qq:{chat_id}",
            role_id=role_id,
            channel="qq",
            chat_id=chat_id,
        )
    )


class _Setup:
    """Role ``mira`` with a QQ account, a group, and the desktop user bound as QQ 100."""

    def __init__(self, tmp_path: Path) -> None:
        manager = SessionManager(tmp_path)
        self.conversation = ConversationService(manager)
        accounts = AccountRegistry({"mira", "other"}.__contains__)
        qq = accounts.register(
            plugin_id="qq",
            platform="qq",
            platform_account_id="10001",
            config_ref="qq-1",
            token="q",
            role_id="mira",
        )
        identities = UserIdentityStore(tmp_path)
        _ = identities.pair(
            identities.create_pairing_code().code,
            record=qq.record,
            user_id="100",
            scope="platform",
            chat=IdentityChat(qq.record.id, "qq", "100"),
        )
        self.group = _thread(self.conversation, role_id="mira", chat_id="gqq:5")
        self.user_chat = _thread(self.conversation, role_id="mira", chat_id="100")
        self.environment = GroupEnvironment(tmp_path, manager.conversation_store)
        self.members = MemberProfiles(tmp_path)
        self.handler = DesktopPhoneMemoryRequestHandler(
            conversations=self.conversation,
            accounts=accounts,
            identities=identities,
            group_environment=self.environment,
            members=self.members,
        )

    def profile(self, sender_id: str, *nicknames: str, thread: ThreadRecord) -> None:
        profile = MemberProfile(
            key=MemberKey("qq", sender_id),
            nicknames=nicknames,
            thread_ids=(thread.id,),
            brief=f"{sender_id} 的速记",
            profile=f"{sender_id} 的档案",
        )
        self.members.write("mira", profile)

    async def call(self, method: str, **payload: object):
        result = await self.handler.handle(method, {"role_id": "mira", **payload})
        assert result is not None
        return result


@pytest.mark.asyncio
async def test_group_note_is_read_and_saved_and_recent_activity_is_read_only(
    tmp_path: Path,
) -> None:
    setup = _Setup(tmp_path)
    group = setup.group.id
    setup.environment.apply(
        "mira",
        GroupEnvironmentUpdate(
            thread_id=group, label="群", recent_activity="在聊开黑", group_note="旧"
        ),
        updated_at=datetime(2026, 9, 29, tzinfo=timezone.utc),
    )

    assert await setup.call("phone.conversation.note", thread_id=group) == {
        "thread_id": group,
        "note": "旧",
    }
    saved = await setup.call(
        "phone.conversation.note.save", thread_id=group, note="## 氛围\n热闹\n"
    )
    assert saved == {"thread_id": group, "note": "## 氛围\n热闹"}
    assert setup.environment.read_note("mira", group) == "## 氛围\n热闹"
    # A blank note removes it.
    _ = await setup.call("phone.conversation.note.save", thread_id=group, note=" ")
    assert not setup.environment.note_path("mira", group).exists()

    assert await setup.call("phone.conversation.activity", thread_id=group) == {
        "thread_id": group,
        "recent_activity": "在聊开黑",
    }
    # No bridge method writes the recent activity.
    assert (
        await setup.handler.handle(
            "phone.conversation.activity.save",
            {"role_id": "mira", "thread_id": group, "recent_activity": "x"},
        )
        is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("original_note", ["", "旧笔记"])
async def test_phone_note_restored_to_original_still_invalidates_old_consolidation(
    tmp_path: Path, original_note: str
) -> None:
    setup = _Setup(tmp_path)
    group = setup.group.id
    setup.environment.apply(
        "mira",
        GroupEnvironmentUpdate(group, "群", "旧摘要", original_note),
        updated_at=datetime(2026, 9, 29, tzinfo=timezone.utc),
    )
    before = setup.environment.read("mira", group)
    for note in ("编辑过的笔记", original_note):
        _ = await setup.call("phone.conversation.note.save", thread_id=group, note=note)
    after = setup.environment.read("mira", group)
    assert after.group_note == before.group_note
    assert after.summary_updated_at == before.summary_updated_at
    assert after.edit_revision == before.edit_revision + 2
    _ = await setup.call(
        "phone.conversation.note.save", thread_id=group, note=original_note
    )
    _ = await setup.call("phone.conversation.note", thread_id=group)
    assert setup.environment.read("mira", group) == after
    assert not commit_external_layers(
        setup.environment,
        setup.members,
        "mira",
        environment_updates=[GroupEnvironmentUpdate(group, "群", "", "旧草稿笔记")],
        member_updates=[],
        snapshot=ExternalLayerSnapshot(group_environments={group: before}),
        updated_at=datetime.now().astimezone(),
    )
    assert setup.environment.read("mira", group) == after


@pytest.mark.asyncio
async def test_only_the_roles_external_conversations_have_chat_info(
    tmp_path: Path,
) -> None:
    setup = _Setup(tmp_path)
    others = _thread(setup.conversation, role_id="other", chat_id="gqq:9")
    desktop = setup.conversation.ensure_desktop_thread("mira")

    for thread_id in (others.id, desktop.id):
        with pytest.raises(ValueError, match="不属于"):
            _ = await setup.call("phone.conversation.note", thread_id=thread_id)
    # The bound user's private chat is user context.
    with pytest.raises(ValueError, match="用户上下文"):
        _ = await setup.call("phone.conversation.members", thread_id=setup.user_chat.id)


@pytest.mark.asyncio
async def test_members_list_leaves_out_the_user_and_other_conversations(
    tmp_path: Path,
) -> None:
    setup = _Setup(tmp_path)
    other_group = _thread(setup.conversation, role_id="mira", chat_id="gqq:6")
    setup.profile("42", "阿花", "花花", thread=setup.group)
    setup.profile("7", "阿草", thread=setup.group)
    setup.profile("8", "路人", thread=other_group)
    # Profiled before 100 was bound as the user.
    setup.profile("100", "主人", thread=setup.group)

    result = await setup.call("phone.conversation.members", thread_id=setup.group.id)

    assert result["thread_id"] == setup.group.id
    assert result["members"] == [
        {
            "channel": "qq",
            "sender_id": "42",
            "call_name": "花花",
            "nicknames": ["阿花", "花花"],
            "brief": "42 的速记",
            "profile": "42 的档案",
        },
        {
            "channel": "qq",
            "sender_id": "7",
            "call_name": "阿草",
            "nicknames": ["阿草"],
            "brief": "7 的速记",
            "profile": "7 的档案",
        },
    ]


@pytest.mark.asyncio
async def test_member_profile_is_read_saved_and_deleted(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)
    group = setup.group.id
    setup.profile("42", "阿花", "花花", thread=setup.group)

    read = await setup.call("phone.member.profile", thread_id=group, sender_id="42")
    assert read["member"]["profile"] == "42 的档案"

    saved = await setup.call(
        "phone.member.profile.save",
        thread_id=group,
        sender_id="42",
        brief=" 爱开黑 ",
        profile="## 印象\n热心\n",
    )
    assert saved["member"]["brief"] == "爱开黑"
    stored = setup.members.read("mira", MemberKey("qq", "42"))
    assert stored is not None
    assert (stored.brief, stored.profile) == ("爱开黑", "## 印象\n热心")
    # The host-kept fields are untouched.
    assert stored.nicknames == ("阿花", "花花")
    assert stored.thread_ids == (group,)

    deleted = await setup.call(
        "phone.member.profile.delete", thread_id=group, sender_id="42"
    )
    assert deleted == {"channel": "qq", "sender_id": "42"}
    assert setup.members.read("mira", MemberKey("qq", "42")) is None
    assert await setup.call(
        "phone.member.profile", thread_id=group, sender_id="42"
    ) == {"member": None}
    # Saving needs an existing profile.
    with pytest.raises(LookupError):
        _ = await setup.call(
            "phone.member.profile.save",
            thread_id=group,
            sender_id="42",
            brief="",
            profile="",
        )


@pytest.mark.asyncio
async def test_the_user_has_no_member_profile(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)
    setup.profile("100", "主人", thread=setup.group)

    for method in ("phone.member.profile", "phone.member.profile.delete"):
        with pytest.raises(ValueError, match="用户本人"):
            _ = await setup.call(method, thread_id=setup.group.id, sender_id="100")
    assert setup.members.read("mira", MemberKey("qq", "100")) is not None


@pytest.mark.asyncio
async def test_a_conversation_only_reaches_members_who_spoke_in_it(
    tmp_path: Path,
) -> None:
    setup = _Setup(tmp_path)
    other_group = _thread(setup.conversation, role_id="mira", chat_id="gqq:6")
    # Same channel, but only ever seen in the other group.
    setup.profile("8", "路人", thread=other_group)

    for method, extra in (
        ("phone.member.profile", {}),
        ("phone.member.profile.save", {"brief": "", "profile": ""}),
        ("phone.member.profile.delete", {}),
    ):
        with pytest.raises(ValueError, match="没有在这个会话出现过"):
            _ = await setup.call(
                method, thread_id=setup.group.id, sender_id="8", **extra
            )
    assert setup.members.read("mira", MemberKey("qq", "8")) is not None
    # From its own conversation it is reachable.
    read = await setup.call(
        "phone.member.profile", thread_id=other_group.id, sender_id="8"
    )
    assert read["member"]["sender_id"] == "8"
