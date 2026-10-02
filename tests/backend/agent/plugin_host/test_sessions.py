"""Host session adapter used by plugins to replace one message's media.

Plugin rules around regeneration (concurrency, NovelAI provenance, failure
handling) are asserted in ``plugins/novelai/tests/test_rpc.py`` against the SDK
``FakeSessions``; this file covers the host side of the same contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.plugin_host.sessions import HostPluginSessions
from desktop_bridge.session_presenter import DesktopSessionPresenter
from session.manager import SessionManager


async def test_replace_message_media_swaps_one_slot_and_projects_the_message(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    before, old, new = (
        tmp_path / name for name in ("before.png", "old.png", "new.png")
    )
    for path in (before, old, new):
        path.write_bytes(path.stem.encode())
    session = manager.get_or_create("role:mira")
    session.add_message("assistant", "scene", media=[str(before), str(old)])
    manager.save(session)
    message_id = str(session.messages[-1]["id"])
    sessions = HostPluginSessions(manager, tmp_path, DesktopSessionPresenter(None))
    slot = {"session_key": session.key, "message_id": message_id}
    current = sessions.get_message_media(**slot, media_index=1)
    first = sessions.get_message_media(**slot, media_index=0)
    assert sessions.original_media_path(current) == str(old)

    payload = await sessions.replace_message_media(
        **slot, media_index=1, expected_path=current, new_path=str(new)
    )

    summary, message = payload["session"], payload["message"]
    assert isinstance(summary, dict) and isinstance(message, dict)
    first_after, copied = message["media"]
    assert summary["key"] == session.key
    assert message["id"] == message_id
    assert first_after == first
    assert copied not in {current, str(new)}
    assert sessions.original_media_path(copied) == str(new)
    new.unlink()
    assert Path(copied).read_bytes() == b"new"
    manager.invalidate(session.key)
    assert sessions.get_message_media(**slot, media_index=1) == copied


async def test_rejected_replacement_keeps_the_old_media_bytes_and_path(
    tmp_path: Path,
) -> None:
    """A stale ``expected_path`` aborts before copying; the old slot stays intact."""
    manager = SessionManager(tmp_path)
    old, new = tmp_path / "old.png", tmp_path / "new.png"
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    session = manager.get_or_create("role:mira")
    session.add_message("assistant", "scene", media=[str(old)])
    manager.save(session)
    sessions = HostPluginSessions(manager, tmp_path, DesktopSessionPresenter(None))
    slot = {
        "session_key": session.key,
        "message_id": str(session.messages[-1]["id"]),
        "media_index": 0,
    }
    current = sessions.get_message_media(**slot)

    with pytest.raises(ValueError, match="已发生变化"):
        await sessions.replace_message_media(
            **slot, expected_path=str(old), new_path=str(new)
        )

    assert current != str(old)
    assert sessions.get_message_media(**slot) == current
    old.unlink()
    assert Path(current).read_bytes() == b"old"
    manager.invalidate(session.key)
    assert sessions.get_message_media(**slot) == current
