from __future__ import annotations

from pathlib import Path

import pytest

from conversation.context_scope import (
    ContextView,
    belongs_to_user,
    desktop_view_thread_ids,
    history_start,
    in_desktop_view,
    load_user_context_threads,
    turn_context_view,
    user_context_view,
)
from conversation.service import desktop_thread_id, network_thread_id
from core.accounts import AccountRecord
from core.identity import IdentityChat, UserIdentityStore
from session.manager import Session

QQ = AccountRecord(
    id="qq:101",
    plugin_id="qq",
    platform="qq",
    platform_account_id="101",
    config_ref="101",
    role_id="mira",
)
DESKTOP = desktop_thread_id("mira")
USER_DM = network_thread_id("mira", "qq", "902")
STRANGER_DM = network_thread_id("mira", "qq", "555")
GROUP = network_thread_id("mira", "qq", "group:7")


def _bind(workspace: Path, chat_id: str) -> None:
    store = UserIdentityStore(workspace)
    identity = store.pair(
        store.create_pairing_code().code,
        record=QQ,
        user_id=chat_id,
        scope="platform",
        chat=IdentityChat(QQ.id, "qq", chat_id),
    )
    assert identity is not None


def _visible(view: ContextView, *threads: str) -> list[str]:
    return [thread for thread in threads if view.includes({"thread_id": thread})]


def test_threads_split_by_the_current_bindings(tmp_path: Path) -> None:
    _bind(tmp_path, "902")
    threads = (DESKTOP, USER_DM, STRANGER_DM, GROUP)

    assert turn_context_view(tmp_path, "mira", DESKTOP).scope == "user"
    assert turn_context_view(tmp_path, "mira", USER_DM).scope == "user"
    assert _visible(turn_context_view(tmp_path, "mira", DESKTOP), *threads) == [
        DESKTOP,
        USER_DM,
    ]
    # An external turn sees only its own conversation (#539): not other groups
    # or stranger private chats.
    other_group = network_thread_id("mira", "qq", "group:8")
    assert _visible(
        turn_context_view(tmp_path, "mira", GROUP), *threads, other_group
    ) == [GROUP]
    assert _visible(
        turn_context_view(tmp_path, "mira", STRANGER_DM), *threads, other_group
    ) == [STRANGER_DM]
    assert _visible(user_context_view(tmp_path, "mira"), *threads) == [
        DESKTOP,
        USER_DM,
    ]


def test_binding_moves_a_private_chat_into_the_user_context(tmp_path: Path) -> None:
    assert turn_context_view(tmp_path, "mira", STRANGER_DM).scope == "external"

    _bind(tmp_path, "555")

    assert turn_context_view(tmp_path, "mira", STRANGER_DM).scope == "user"


def test_legacy_messages_without_a_thread_belong_to_the_user_context(
    tmp_path: Path,
) -> None:
    message = {"role": "user", "content": "legacy"}

    assert user_context_view(tmp_path, "mira").includes(message)
    assert not turn_context_view(tmp_path, "mira", GROUP).includes(message)
    # A message still in memory carries its thread in metadata only.
    assert not turn_context_view(tmp_path, "mira", GROUP).includes(
        {"metadata": {"thread_id": DESKTOP}}
    )


def test_desktop_view_is_only_the_desktop_conversation(tmp_path: Path) -> None:
    _bind(tmp_path, "902")
    scheduler = "thread:mira:scheduler:job-1"
    threads = ["", DESKTOP, scheduler, USER_DM, STRANGER_DM, GROUP]

    # A bound user's private chat is user context but not the desktop view.
    assert user_context_view(tmp_path, "mira").includes_thread(USER_DM)
    assert not in_desktop_view("mira", USER_DM)
    assert desktop_view_thread_ids("mira", threads) == {"", DESKTOP, scheduler}
    assert not in_desktop_view("mira", desktop_thread_id("other"))


@pytest.mark.parametrize(
    ("thread_id", "sender_is_user", "expected"),
    [
        (DESKTOP, False, True),
        (USER_DM, False, True),
        (STRANGER_DM, False, False),
        (GROUP, True, True),
        (GROUP, False, False),
    ],
    ids=["desktop", "bound-dm", "stranger-dm", "user-in-group", "group-member"],
)
def test_belongs_to_user_by_thread_or_sender_flag(
    tmp_path: Path, thread_id: str, sender_is_user: bool, expected: bool
) -> None:
    _bind(tmp_path, "902")
    source: dict[str, object] = {"channel": "qq", "sender_id": "902"}
    if sender_is_user:
        source["sender_is_user"] = True
    message = {
        "role": "user",
        "thread_id": thread_id,
        "metadata": {"message_source": source},
    }

    user_threads = load_user_context_threads(tmp_path, "mira")

    assert belongs_to_user(message, user_threads) is expected


def test_each_context_reads_history_from_its_own_cursor(tmp_path: Path) -> None:
    """旧会话迁移时两类都从原 last_consolidated 起读；有按上下文游标后各读各的。"""
    session = Session("role:mira")
    for index, thread in enumerate((DESKTOP, GROUP, DESKTOP, GROUP, DESKTOP, GROUP)):
        session.add_message("user", f"m{index}", thread_id=thread)
    session.last_consolidated = 2
    user = user_context_view(tmp_path, "mira")
    external = turn_context_view(tmp_path, "mira", GROUP)

    def history(view: ContextView, start: int) -> list[str]:
        return [
            str(message["content"])
            for message in session.history_window(
                500, start_index=start, include=view.includes
            )
        ]

    # 迁移前的读取方式：两类都从 last_consolidated 起。
    before = {view.scope: history(view, 2) for view in (user, external)}
    assert {
        view.scope: history(view, history_start(session, view))
        for view in (user, external)
    } == before
    assert history_start(session, None) == 2

    session.context_cursors = {"user": 0, "external": 5}
    assert history(user, history_start(session, user)) == ["m0", "m2", "m4"]
    assert history(external, history_start(session, external)) == ["m5"]
    assert history_start(session, None) == 2
