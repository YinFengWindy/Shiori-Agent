from __future__ import annotations

from pathlib import Path

import pytest

from conversation.store import ConversationStore
from core.desktop_presence import DesktopPresence
from core.roles import RoleStore
from desktop_bridge.runtime.proactive_target import preview_proactive_target
from proactive_v2.target_selection import ProactiveTargetResolver
from session.store import SessionStore

_DESKTOP = {"channel": "desktop", "chat_id": "role:mira"}
_QQ_PRIVATE = {"channel": "qq", "chat_id": "10001"}
_QQ_GROUP = {"channel": "qq", "chat_id": "gqq:7"}


@pytest.fixture
def preview(tmp_path: Path):
    roles = RoleStore(tmp_path)
    _ = roles.create_role(
        role_id="mira", name="Mira", description="", system_prompt="you are mira"
    )
    sessions = SessionStore(tmp_path / "sessions.db")
    sessions.create_session(key="role:mira", metadata={"role_id": "mira"})
    sessions.insert_message(
        "role:mira",
        role="user",
        content="hi",
        ts="2026-09-25T10:00:00+08:00",
        seq=0,
        thread_id="thread:mira:qq:gqq:7",
    )
    sessions.close()
    presence = DesktopPresence()
    conversations = ConversationStore(tmp_path / "sessions.db")
    resolver = ProactiveTargetResolver(
        roles=roles, conversations=conversations, desktop_presence=presence
    )
    yield presence, lambda payload: preview_proactive_target(roles, resolver, payload)
    conversations.close()


def test_preview_selects_among_unsaved_candidates_by_the_delivery_rule(preview):
    presence, run = preview

    assert run({"role_id": "mira", "candidates": [_DESKTOP, _QQ_PRIVATE]}) == {
        "target": _DESKTOP
    }
    presence.report(False)
    # The group has the latest user message; the role has saved no candidates.
    assert run(
        {"role_id": "mira", "candidates": [_DESKTOP, _QQ_PRIVATE, _QQ_GROUP]}
    ) == {"target": _QQ_GROUP}
    assert run({"role_id": "mira", "candidates": [_DESKTOP, _QQ_PRIVATE]}) == {
        "target": _QQ_PRIVATE
    }


def test_preview_without_candidates_has_no_target(preview):
    _, run = preview

    assert run({"role_id": "mira", "candidates": []}) == {"target": None}


@pytest.mark.parametrize(
    ("payload", "error", "match"),
    [
        ({"role_id": "luna", "candidates": []}, KeyError, "角色不存在"),
        ({"role_id": "mira"}, ValueError, "candidates"),
        ({"role_id": "mira", "candidates": [{"channel": "qq"}]}, ValueError, "chat_id"),
    ],
)
def test_preview_rejects_invalid_requests(preview, payload, error, match):
    _, run = preview

    with pytest.raises(error, match=match):
        run(payload)
