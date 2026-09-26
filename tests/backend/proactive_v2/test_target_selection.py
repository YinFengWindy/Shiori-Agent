from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from conversation.store import ConversationStore
from core.desktop_presence import DesktopPresence
from core.roles import RoleProactiveCandidate, RoleStore
from proactive_v2.target_selection import (
    ProactiveTargetResolver,
    select_proactive_target,
)
from session.store import SessionStore

DESKTOP = RoleProactiveCandidate("desktop", "role:mira")
QQ_PRIVATE = RoleProactiveCandidate("qq", "10001")
QQ_GROUP = RoleProactiveCandidate("qq", "gqq:7")
NOW = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)


def test_present_desktop_candidate_wins_over_recent_external_chat() -> None:
    assert (
        select_proactive_target(
            [QQ_PRIVATE, DESKTOP],
            desktop_present=True,
            last_user_at={QQ_PRIVATE: NOW},
        )
        == DESKTOP
    )


def test_away_user_gets_the_most_recently_used_external_candidate() -> None:
    target = select_proactive_target(
        [DESKTOP, QQ_PRIVATE, QQ_GROUP],
        desktop_present=False,
        last_user_at={QQ_PRIVATE: NOW - timedelta(hours=1), QQ_GROUP: NOW},
    )

    assert target == QQ_GROUP


def test_desktop_presence_is_ignored_when_desktop_is_not_a_candidate() -> None:
    target = select_proactive_target(
        [QQ_PRIVATE, QQ_GROUP],
        desktop_present=True,
        last_user_at={QQ_GROUP: NOW},
    )

    assert target == QQ_GROUP


def test_without_history_the_first_external_candidate_in_binding_order_wins() -> None:
    target = select_proactive_target(
        [DESKTOP, QQ_GROUP, QQ_PRIVATE], desktop_present=False, last_user_at={}
    )

    assert target == QQ_GROUP


def test_equal_times_keep_binding_order() -> None:
    target = select_proactive_target(
        [QQ_GROUP, QQ_PRIVATE],
        desktop_present=False,
        last_user_at={QQ_PRIVATE: NOW, QQ_GROUP: NOW},
    )

    assert target == QQ_GROUP


def test_desktop_only_candidates_keep_the_desktop_while_away() -> None:
    assert (
        select_proactive_target([DESKTOP], desktop_present=False, last_user_at={})
        == DESKTOP
    )


def test_no_candidate_is_an_error() -> None:
    with pytest.raises(ValueError, match="没有可用的接收会话"):
        _ = select_proactive_target([], desktop_present=True, last_user_at={})


def test_enabled_role_without_legacy_candidate_can_choose_account_target(
    tmp_path: Path,
) -> None:
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="mira")
    roles.update_role("mira", proactive={"enabled": True, "candidates": []})
    resolver = ProactiveTargetResolver(
        roles=roles,
        conversations=SimpleNamespace(last_user_message_at=lambda thread_id: None),
        desktop_presence=SimpleNamespace(is_desktop_present=lambda: False),
    )
    assert resolver.resolve_saved("mira") == DESKTOP


def _write_user_message(db: Path, *, seq: int, thread_id: str, ts: str) -> None:
    store = SessionStore(db)
    try:
        if seq == 0:
            store.create_session(key="role:mira", metadata={"role_id": "mira"})
        store.insert_message(
            "role:mira",
            role="user",
            content="hi",
            ts=ts,
            seq=seq,
            thread_id=thread_id,
        )
    finally:
        store.close()


def _resolver(tmp_path: Path, presence: DesktopPresence) -> ProactiveTargetResolver:
    roles = RoleStore(tmp_path)
    _ = roles.create_role(
        role_id="mira", name="Mira", description="", system_prompt="you are mira"
    )
    _ = roles.update_role(
        "mira",
        channel_bindings=[
            {"channel": "desktop", "chat_id": "role:mira", "chat_type": "private"},
            {"channel": "qq", "chat_id": "10001", "chat_type": "private"},
            {"channel": "qq", "chat_id": "gqq:7", "chat_type": "group"},
        ],
        proactive={
            "enabled": True,
            "candidates": [
                {"channel": "desktop", "chat_id": "role:mira"},
                {"channel": "qq", "chat_id": "10001"},
                {"channel": "qq", "chat_id": "gqq:7"},
            ],
        },
    )
    return ProactiveTargetResolver(
        roles=roles,
        conversations=ConversationStore(tmp_path / "sessions.db"),
        desktop_presence=presence,
    )


def test_resolver_reads_user_messages_per_candidate_thread(tmp_path: Path) -> None:
    db = tmp_path / "sessions.db"
    _write_user_message(
        db, seq=0, thread_id="thread:mira:qq:10001", ts="2026-09-25T10:00:00+08:00"
    )
    _write_user_message(
        db, seq=1, thread_id="thread:mira:qq:gqq:7", ts="2026-09-25T11:00:00+08:00"
    )
    # A newer desktop message never makes an external candidate more recent.
    _write_user_message(
        db, seq=2, thread_id="thread:mira:desktop", ts="2026-09-25T12:00:00+08:00"
    )
    presence = DesktopPresence()
    resolver = _resolver(tmp_path, presence)

    assert resolver.resolve_saved("mira") == DESKTOP
    presence.report(False)
    assert resolver.resolve_saved("mira") == QQ_GROUP
    # An unsaved candidate list is resolved by the same rule.
    assert resolver.resolve("mira", [DESKTOP, QQ_PRIVATE]) == QQ_PRIVATE


def test_resolver_uses_first_external_candidate_without_history(
    tmp_path: Path,
) -> None:
    presence = DesktopPresence()
    presence.report(False)

    assert _resolver(tmp_path, presence).resolve_saved("mira") == QQ_PRIVATE


def test_resolver_has_no_target_for_a_role_without_candidates(tmp_path: Path) -> None:
    resolver = _resolver(tmp_path, DesktopPresence())
    RoleStore(tmp_path).update_role("mira", proactive={"enabled": False})

    assert resolver.resolve_saved("mira") is None
    with pytest.raises(KeyError, match="角色不存在"):
        _ = resolver.resolve_saved("luna")
