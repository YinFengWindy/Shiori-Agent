"""HostExternalTurns.submit runs a submission as an external group turn (#721)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from conversation.context_scope import in_desktop_view, turn_context_view
from conversation.listening import GroupListeningControl
from conversation.service import ConversationService
from core.accounts import AccountRegistry
from core.channel_avatars import ChannelAvatarStore
from core.identity import UserIdentityStore
from core.memory.markdown.external_segment import group_external_threads
from core.memory.markdown.formatting import (
    _select_consolidation_window,
    split_consolidation_window,
)
from core.memory.member_profiles import MemberKey, MemberProfile, MemberProfiles
from desktop_bridge.phone_requests import DesktopPhoneRequestHandler
from desktop_bridge.session_presenter import DesktopSessionPresenter
from prompts.agent import EXTERNAL_TURN_RULES_PROMPT
from session.manager import SessionManager
from shiori_sdk.external_turns import ExternalTurnMessage
from tests.support.external_turns import (
    ROOM,
    ROOM_TITLE,
    SECRETS,
    ExternalTurnHost,
    request_text,
    room_message,
    tool_names,
)


@pytest.fixture
def host(tmp_path: Path) -> ExternalTurnHost:
    return ExternalTurnHost(tmp_path)


async def test_submission_is_an_external_group_turn_in_its_own_thread(host):
    host.group_environment.write_note("mira", ROOM, "ROOM-NOTE")
    MemberProfiles(host.manager.workspace).write(
        "mira",
        MemberProfile(
            MemberKey("bilibili", "uid-7"),
            ("观众七",),
            (ROOM,),
            brief="速记",
            profile="VIEWER-PROFILE",
        ),
    )
    # Positive control: a desktop turn sees the user context and every tool.
    assert await host.desktop_turn("hello") == "reply-1"
    desktop_request = host.provider.requests[0]
    assert all(secret in request_text(desktop_request) for secret in SECRETS)
    assert {"user_only", "public"} <= tool_names(desktop_request)

    result = await host.turns.submit(room_message())

    assert (result.status, result.reply) == ("replied", "reply-2")
    text = request_text(host.provider.requests[1])
    assert not any(secret in text for secret in SECRETS)
    # What an external turn gets through the existing mechanisms.
    for injected in (
        EXTERNAL_TURN_RULES_PROMPT,
        "SELF-PERSONA",
        "SELF-RELATIONSHIP",
        "ROOM-NOTE",
        "VIEWER-PROFILE",
    ):
        assert injected in text
    # The sender is a group member, never the bound user.
    assert "群友「观众七」（ID uid-7）" in text
    assert tool_names(host.provider.requests[1]) & {"user_only", "public"} == {"public"}
    assert host.stored(ROOM) == [("user", "主播好"), ("assistant", "reply-2")]
    assert not in_desktop_view("mira", ROOM)


async def test_submission_is_listed_in_the_phone_and_consolidated_externally(host):
    await host.turns.submit(room_message())

    workspace = host.manager.workspace
    conversation = ConversationService(SessionManager(workspace))
    phone = DesktopPhoneRequestHandler(
        conversations=conversation,
        accounts=AccountRegistry({"mira"}.__contains__),
        identities=UserIdentityStore(workspace),
        messages=DesktopSessionPresenter(conversation),
        avatars=ChannelAvatarStore(workspace),
        listening=GroupListeningControl(conversation, lambda _channel: False),
    )
    listed = await phone.handle("phone.conversations.list", {"role_id": "mira"})
    assert listed is not None
    row = next(row for row in listed["conversations"] if row["thread_id"] == ROOM)
    assert (row["display_name"], row["channel"], row["chat_type"]) == (
        ROOM_TITLE,
        "bilibili",
        "group",
    )
    assert (row["account_id"], row["is_user_chat"]) == (None, False)
    # The external context's consolidation window (its own cursor) takes the
    # room, with the viewer as a member to profile.
    session = SessionManager(workspace).get_or_create("role:mira")
    view = turn_context_view(workspace, "mira", ROOM).category
    window = _select_consolidation_window(
        session,
        keep_count=0,
        consolidation_min_new_messages=1,
        archive_all=False,
        force=True,
        views=(view,),
    )
    assert window is not None
    threads = group_external_threads(
        window,
        split_consolidation_window(window, view.user_threads),
        host.roles.bound_user_senders("mira"),
    )
    assert [thread.thread_id for thread in threads] == [ROOM]
    assert [member.key for member in threads[0].members] == [
        MemberKey("bilibili", "uid-7")
    ]


async def test_replayed_message_id_runs_nothing(host):
    assert (await host.turns.submit(room_message())).status == "replied"

    result = await host.turns.submit(room_message("again"))

    assert result.status == "duplicate"
    assert len(host.provider.requests) == 1
    assert host.stored(ROOM) == [("user", "主播好"), ("assistant", "reply-1")]


async def test_busy_role_returns_busy_at_once_and_leaves_no_trace(host):
    gate = asyncio.Event()
    host.provider.gates.append(gate)
    desktop = host.desktop_turn("hello")
    await host.provider.started.wait()

    result = await asyncio.wait_for(host.turns.submit(room_message()), timeout=1)

    assert result.status == "busy"
    gate.set()
    assert await desktop == "reply-1"
    assert len(host.provider.requests) == 1
    # Neither the room's thread nor its contact exists.
    conversation = ConversationService(SessionManager(host.manager.workspace))
    assert conversation.get_thread(ROOM) is None
    assert not any(
        "bilibili" in contact_id for contact_id in conversation.contacts_by_id("mira")
    )


@pytest.mark.parametrize(
    ("change", "error"),
    [({"role_id": "nobody"}, "角色不存在"), ({"platform": "desktop"}, "宿主渠道名")],
)
async def test_unknown_role_or_host_transport_is_rejected(host, change, error):
    fields = {**room_message().__dict__, **change}

    with pytest.raises(ValueError, match=error):
        await host.turns.submit(ExternalTurnMessage(**fields))
    assert host.provider.requests == []
