"""Host session adapter used by plugins to replace one message's media.

Plugin rules around regeneration (concurrency, NovelAI provenance, failure
handling) are asserted in ``plugins/novelai/tests/test_rpc.py`` against the SDK
``FakeSessions``; this file covers the host side of the same contract.
"""

from __future__ import annotations

from pathlib import Path

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
